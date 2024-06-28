import pytest
import random
from typing import Optional, Deque
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle
from amaranth import *

from transactron.lib import Adapter
from transactron.utils import ModuleConnector, RecordIntDict
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, SimpleTestCircuit, TestGen
from transactron.utils.dependencies import DependencyContext

from coreblocks.frontend import FrontendParams
from coreblocks.frontend.fetch.fetch_target_queue import FetchTargetQueue
from coreblocks.frontend.branch_prediction.iface import BranchPredictionUnitInterface
from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.interface.keys import FetchResumeKey
from coreblocks.interface.layouts import BranchPredictionLayouts


class MockBPU(Elaboratable, BranchPredictionUnitInterface):
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(BranchPredictionLayouts)

        self.request_io = TestbenchIO(Adapter(i=layouts.bpu_request))
        self.read_target_pred_io = TestbenchIO(Adapter(o=layouts.bpu_read_target_pred))
        self.read_pred_details_io = TestbenchIO(Adapter(o=layouts.bpu_read_pred_details))
        self.update_io = TestbenchIO(Adapter())
        self.flush_io = TestbenchIO(Adapter(nonexclusive=True))

        self.request = self.request_io.adapter.iface
        self.read_target_pred = self.read_target_pred_io.adapter.iface
        self.read_pred_details = self.read_pred_details_io.adapter.iface
        self.update = self.update_io.adapter.iface
        self.flush = self.flush_io.adapter.iface

    def elaborate(self, platform):
        m = Module()

        m.submodules.request_io = self.request_io
        m.submodules.read_target_pred_io = self.read_target_pred_io
        m.submodules.read_pred_details_io = self.read_pred_details_io
        m.submodules.update_io = self.update_io
        m.submodules.flush_io = self.flush_io

        return m


@dataclass(frozen=True)
class FTQIndex:
    ptr: int
    parity: bool

    def as_dict(self) -> RecordIntDict:
        return {"parity": self.parity, "ptr": self.ptr}


@dataclass(frozen=True)
class BPURequest:
    pc: int
    ftq_idx: FTQIndex
    global_branch_history: int = 0
    bpu_stage: int = 0


@dataclass(frozen=True)
class BlockPrediction:
    branch_mask: int
    cfi_idx: int
    cfi_type: CfiType
    cfi_target: Optional[int]

    def as_dict(self) -> RecordIntDict:
        return {
            "branch_mask": self.branch_mask,
            "cfi_idx": self.cfi_idx,
            "cfi_type": int(self.cfi_type),
            "maybe_cfi_target": {
                "valid": self.cfi_target is not None,
                "value": self.cfi_target if self.cfi_target is not None else 0,
            },
        }


@dataclass(frozen=True)
class IFURequest:
    pc: int
    ftq_idx: FTQIndex
    bpu_stage: int = 0


@dataclass(frozen=True)
class IFUResponse:
    block_prediction: BlockPrediction
    redirect: bool = False
    unsafe: bool = False


class TestFTQ(TestCaseWithSimulator):
    fetch_block_log: int
    start_pc: int = 0x100
    ftq_size_log: int = 4

    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        random.seed(41)

    def init_module(self, bpu_stages_cnt) -> None:
        self.bpu_stages_cnt = bpu_stages_cnt

        self.gen_params = GenParams(
            test_core_config.replace(
                start_pc=self.start_pc,
                ftq_size_log=self.ftq_size_log,
                fetch_block_bytes_log=3,
                compressed=True,
            )
        )

        # Override directly in genparams
        self.gen_params.bpu_stages_cnt = bpu_stages_cnt

        self.bpu = MockBPU(self.gen_params)
        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params, self.bpu))
        self.fetch_resume_mock = TestbenchIO(Adapter())
        DependencyContext.get().add_dependency(FetchResumeKey(), self.fetch_resume_mock.adapter.iface)

        self.m = ModuleConnector(self.bpu, self.ftq)

        self.expected_bpu_requests: Deque[tuple[BPURequest, list[Optional[tuple[int, int]]], BlockPrediction]] = deque()
        self.bpu_target_resp: list[Optional[RecordIntDict]] = [None] * (self.bpu_stages_cnt + 1)
        self.bpu_details_resp: list[Optional[RecordIntDict]] = [None] * (self.bpu_stages_cnt + 1)

        self.expected_ifu_requests: Deque[tuple[IFURequest, IFUResponse]] = deque()
        self.fetched_pcs: list[int] = []

    @def_method_mock(
        lambda self: self.bpu.request_io, enable=lambda self: len(self.expected_bpu_requests) > 0, sched_prio=2
    )
    def bpu_req_mock(self, pc, ftq_idx, global_branch_history, bpu_stage):
        req, targets, pred = self.expected_bpu_requests.popleft()
        assert pc == req.pc
        assert ftq_idx == req.ftq_idx.as_dict()
        assert global_branch_history == req.global_branch_history
        assert bpu_stage == req.bpu_stage

        for i, target in enumerate(targets):
            if target is None or self.bpu_target_resp[i + 1] is not None:
                continue

            self.bpu_target_resp[i + 1] = {
                "ftq_idx": req.ftq_idx.as_dict(),
                "pc": target[0],
                "bpu_stage": i,
                "global_branch_history": target[1],
            }

        self.bpu_details_resp[self.bpu_stages_cnt] = {
            "ftq_idx": req.ftq_idx.as_dict(),
            "bpu_stage": req.bpu_stage,
            "bpu_meta": 0,
            "block_prediction": pred.as_dict(),
        }

    @def_method_mock(
        lambda self: self.bpu.read_target_pred_io, enable=lambda self: self.bpu_target_resp[0] is not None, sched_prio=1
    )
    def bpu_target_pred_mock(self):
        return self.bpu_target_resp[0]

    @def_method_mock(
        lambda self: self.bpu.read_pred_details_io,
        enable=lambda self: self.bpu_details_resp[0] is not None,
        sched_prio=1,
    )
    def bpu_pred_details_mock(self):
        return self.bpu_details_resp[0]

    @def_method_mock(lambda self: self.bpu.update_io)
    def bpu_update_mock(self):
        pass

    @def_method_mock(lambda self: self.bpu.flush_io, sched_prio=4)
    def bpu_flush_mock(self):
        for i in range(self.bpu_stages_cnt):
            self.bpu_target_resp[i + 1] = None
            self.bpu_details_resp[i + 1] = None

    # This process simulates the pipeline inside the BPU - simply moves data forward
    def bpu_process(self):
        yield Passive()
        while True:
            yield
            for i in range(self.bpu_stages_cnt):
                self.bpu_target_resp[i] = self.bpu_target_resp[i + 1]
                self.bpu_details_resp[i] = self.bpu_details_resp[i + 1]

            self.bpu_target_resp[self.bpu_stages_cnt] = None
            self.bpu_details_resp[self.bpu_stages_cnt] = None

    def ifu_processes(self, latency: int):
        pipeline: list[Optional[tuple[IFURequest, IFUResponse]]] = [None] * (latency + 1)

        def input():
            yield Passive()
            while True:
                yield from self.multi_settle(2)
                if len(self.expected_ifu_requests) == 0:
                    yield
                    continue

                req, resp = self.expected_ifu_requests.popleft()
                pipeline[latency] = (req, resp)

                fetch_target = yield from self.ftq.consume_fetch_target.call()
                assert fetch_target["pc"] == req.pc
                assert fetch_target["ftq_idx"] == req.ftq_idx.as_dict()
                assert fetch_target["bpu_stage"] == req.bpu_stage

        def output():
            yield Passive()
            while True:
                yield from self.multi_settle(3)
                req_resp = pipeline[0]
                for i in range(latency):
                    pipeline[i] = pipeline[i + 1]
                pipeline[latency] = None

                if req_resp is None:
                    yield
                    continue

                req, resp = req_resp

                yield from self.ftq.consume_prediction.call_init(ftq_idx=req.ftq_idx.as_dict(), bpu_stage=req.bpu_stage)
                yield Settle()
                while (res := (yield from self.ftq.consume_prediction.call_result())) is None:
                    yield
                    yield from self.multi_settle(3)

                if not res["discard"]:
                    yield from self.ftq.ifu_writeback.call(
                        ftq_idx=req.ftq_idx.as_dict(),
                        fb_addr=FrontendParams(self.gen_params).fb_addr(C(req.pc, self.gen_params.isa.xlen)),
                        redirect=resp.redirect,
                        unsafe=resp.unsafe,
                        block_prediction=resp.block_prediction.as_dict(),
                    )

                    self.fetched_pcs.append(req.pc)
                else:
                    yield
                yield from self.ftq.consume_prediction.disable()

        return (input, output)

    def expect_bpu_request(self, req: BPURequest, targets: list[Optional[tuple[int, int]]], pred: BlockPrediction):
        assert len(targets) == self.bpu_stages_cnt
        self.expected_bpu_requests.append((req, targets, pred))

    def expect_ifu_request(self, req: IFURequest, resp: IFUResponse):
        self.expected_ifu_requests.append((req, resp))

    def read_jump_target(self, ftq_idx: FTQIndex) -> TestGen[Optional[int]]:
        yield from self.ftq.jump_target_req.call(ftq_idx=ftq_idx.as_dict())
        ret = yield from self.ftq.jump_target_resp.call()
        return None if ~ret["maybe_cfi_target"]["valid"] else ret["maybe_cfi_target"]["value"]

    def commit_block(self, ftq_idx: FTQIndex, last_instr_offset: int = -1):
        for i in range(self.gen_params.fetch_width + last_instr_offset + 1):
            yield from self.ftq.commit.call(ftq_idx=ftq_idx.as_dict(), fb_instr_idx=i, exception=0, misprediction=0)

    def run_sim(self, test_proc: Callable[[], TestGen[None]], ifu_latency: int = 3):
        with self.run_simulation(self.m) as sim:
            ifu_in, ifu_out = self.ifu_processes(ifu_latency)
            sim.add_sync_process(ifu_in)
            sim.add_sync_process(ifu_out)
            sim.add_sync_process(self.bpu_process)
            sim.add_sync_process(test_proc)

    def test_ifu_faster_than_bpu(self):
        """Tests what happens when IFU delivers the fetch block faster than BPU makes the prediction."""

        self.init_module(bpu_stages_cnt=3)

        def test_proc():
            yield from self.tick(2)

            # Enable IFU while keep blocking BPU
            self.expect_ifu_request(
                IFURequest(0x100, FTQIndex(0, False), 0),
                IFUResponse(BlockPrediction(0, self.gen_params.fetch_width - 1, CfiType.INVALID, None)),
            )
            yield from self.tick(5)

            # Nothing should leave IFU until we get the prediction details
            assert len(self.fetched_pcs) == 0

            # Enable BPU for one request
            self.expect_bpu_request(
                BPURequest(0x100, FTQIndex(0, False)),
                [(0x200, 0x0), None, None],
                BlockPrediction(0, 0, CfiType.INVALID, None),
            )

            yield from self.tick(10)

            assert self.fetched_pcs == [0x100]

            # Simultaneously enable IFU and BPU
            for i in range(1, 5):
                pc = (i + 1) * 0x100
                ftq_idx = FTQIndex(i, False)
                self.expect_bpu_request(
                    BPURequest(pc, ftq_idx),
                    [(pc + 0x100, 0x0), None, None],
                    BlockPrediction(0, 0, CfiType.INVALID, None),
                )
                self.expect_ifu_request(
                    IFURequest(pc, ftq_idx, 0),
                    IFUResponse(BlockPrediction(0, self.gen_params.fetch_width - 1, CfiType.INVALID, None)),
                )

            yield from self.tick(20)

        self.run_sim(test_proc, ifu_latency=2)

    def test_full_ftq(self):
        """Tests what happens when the FTQ is fully filled by BPU."""

        self.init_module(bpu_stages_cnt=1)

        def test_proc():
            yield from self.tick(2)

            # Fill the whole FTQ with predictions and simultaneously send them to the IFU
            for i in range(self.gen_params.ftq_size):
                pc = (i + 1) * 0x100
                ftq_idx = FTQIndex(i, False)
                self.expect_bpu_request(
                    BPURequest(pc, ftq_idx), [(pc + 0x100, 0x0)], BlockPrediction(0, 0, CfiType.INVALID, None)
                )
                self.expect_ifu_request(
                    IFURequest(pc, ftq_idx, 0),
                    IFUResponse(BlockPrediction(0, self.gen_params.fetch_width - 1, CfiType.INVALID, None)),
                )
            yield from self.tick(30)

            # There should be exactly one unconsumed BPU request - we can't make
            # a prediction for the last FTQ entry until there's more space in the FTQ.
            assert len(self.expected_bpu_requests) == 1
            self.expected_bpu_requests.clear()
            # Make sure that all FTQ entries were fetched
            assert len(self.expected_ifu_requests) == 0
            assert self.fetched_pcs == [0x100 * (i + 1) for i in range(self.gen_params.ftq_size - 1)]

            yield

            # Commit everything except the last one (we didn't make a prediction for it yet)
            for i in range(self.gen_params.ftq_size - 1):
                yield from self.commit_block(FTQIndex(i, False))

            yield from self.tick(5)

            # This is prediction for the last FTQ entry
            self.expect_bpu_request(
                BPURequest((self.gen_params.ftq_size) * 0x100, FTQIndex(self.gen_params.ftq_size - 1, False)),
                [(0x5000, 0x0)],
                BlockPrediction(0, 0, CfiType.INVALID, None),
            )

            # Keep IFU disabled and let BPU make predictions
            for i in range(self.gen_params.ftq_size):
                pc = i * 0x100 + 0x5000
                ftq_idx = FTQIndex(i, True)
                self.expect_bpu_request(
                    BPURequest(pc, ftq_idx), [(pc + 0x100, 0x0)], BlockPrediction(0, 0, CfiType.INVALID, None)
                )

            yield from self.tick(10)

            # Commit the last one
            yield from self.commit_block(FTQIndex(self.gen_params.ftq_size - 1, False))

            yield from self.tick(20)

            # Again, only one should be left
            assert len(self.expected_bpu_requests) == 1

        self.run_sim(test_proc)

    def test_last_instr_offset(self):
        """Tests if the FTQ commits blocks correctly when the last instruction in a block is on different positions."""

        self.init_module(bpu_stages_cnt=1)

        def test_proc():
            yield from self.tick(2)

            # Realistically only these offsets are possible. To see why, consider all possible
            # positions of the last instruction with C extension turned on.
            for i, offset in enumerate([-1, -2, -3]):
                pc = (i + 1) * 0x100
                self.expect_bpu_request(
                    BPURequest(pc, FTQIndex(i, False)), [(pc + 0x100, 0)], BlockPrediction(0, 0, CfiType.INVALID, None)
                )

                # Assume that the last instruction in the block is on position `self.gen_params.fetch_width - 2`.
                self.expect_ifu_request(
                    IFURequest(pc, FTQIndex(i, False), 0),
                    IFUResponse(BlockPrediction(0, self.gen_params.fetch_width + offset, CfiType.INVALID, None)),
                )

                yield from self.tick(10)
                yield from self.commit_block(FTQIndex(i, False), last_instr_offset=offset)
                yield from self.tick(10)

            # Now all of these predictions should fit in the FTQ if the previous FTQ entries were commited successfully.
            for i in range(3, self.gen_params.ftq_size + 2):
                pc = (i + 1) * 0x100
                ftq_idx = FTQIndex(i % self.gen_params.ftq_size, i >= self.gen_params.ftq_size)
                self.expect_bpu_request(
                    BPURequest(pc, ftq_idx), [(pc + 0x100, 0)], BlockPrediction(0, 0, CfiType.INVALID, None)
                )

            yield from self.tick(20)

            assert len(self.expected_bpu_requests) == 0

        self.run_sim(test_proc)

    def test_prediction_override(self):
        """Tests prediction overrides."""
        self.init_module(bpu_stages_cnt=3)

        def test_proc():
            yield from self.tick(2)

            # Firstly make a few BPU predictions
            for i in range(3):
                pc = (i + 1) * 0x100
                self.expect_bpu_request(
                    BPURequest(pc, FTQIndex(i, False)),
                    [(pc + 0x100, 0), None],
                    BlockPrediction(0, 0, CfiType.INVALID, None),
                )

            yield from self.tick(10)

            # Make the IFU redirect the FTQ
            self.expect_ifu_request(
                IFURequest(0x100, FTQIndex(0, False), 0),
                IFUResponse(BlockPrediction(0, self.gen_params.fetch_width - 1, CfiType.JAL, 0x1000), redirect=True),
            )

            # Now verify the moment when the redirection propagates to the BPU
            for i in range(3, 7):
                pc = (i + 1) * 0x100
                self.expect_bpu_request(
                    BPURequest(pc, FTQIndex(i, False)),
                    [(pc + 0x100, 0), None],
                    BlockPrediction(0, 0, CfiType.INVALID, None),
                )
            # It takes 3 cycles for IFU to verify the prediction and 1 cycle to redirect the FTQ, so
            # the 5th prediction should reflect the redirection.
            self.expect_bpu_request(
                BPURequest(0x1000, FTQIndex(1, False)),
                [(0x1100, 0), None],
                BlockPrediction(0, 0, CfiType.INVALID, None),
            )

            yield from self.tick(15)

            assert self.fetched_pcs == [0x100]

        self.run_sim(test_proc, ifu_latency=3)

    def test_ifu_redirect(self):
        """Tests the case when the fetch unit makes a redirection."""
        self.init_module(bpu_stages_cnt=2)

        def test_proc():
            yield from self.tick(2)

            # Firstly make a few BPU predictions
            for i in range(3):
                pc = (i + 1) * 0x100
                self.expect_bpu_request(
                    BPURequest(pc, FTQIndex(i, False)),
                    [(pc + 0x100, 0), None],
                    BlockPrediction(0, 0, CfiType.INVALID, None),
                )

            yield from self.tick(10)

            # Make the IFU redirect the FTQ
            self.expect_ifu_request(
                IFURequest(0x100, FTQIndex(0, False), 0),
                IFUResponse(BlockPrediction(0, self.gen_params.fetch_width - 1, CfiType.JAL, 0x1000), redirect=True),
            )

            # Now verify the moment when the redirection propagates to the BPU
            for i in range(3, 7):
                pc = (i + 1) * 0x100
                self.expect_bpu_request(
                    BPURequest(pc, FTQIndex(i, False)),
                    [(pc + 0x100, 0), None],
                    BlockPrediction(0, 0, CfiType.INVALID, None),
                )
            # It takes 3 cycles for IFU to verify the prediction and 1 cycle to redirect the FTQ, so
            # the 5th prediction should reflect the redirection.
            self.expect_bpu_request(
                BPURequest(0x1000, FTQIndex(1, False)),
                [(0x1100, 0), None],
                BlockPrediction(0, 0, CfiType.INVALID, None),
            )

            yield from self.tick(15)

            assert self.fetched_pcs == [0x100]

        self.run_sim(test_proc, ifu_latency=3)
