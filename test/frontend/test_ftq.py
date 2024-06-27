import pytest
from parameterized import parameterized_class
import random
from typing import Optional, Deque
from collections import deque
from dataclasses import dataclass

from amaranth import Elaboratable, Module
from amaranth.sim import Passive, Settle
from amaranth import *

from transactron.lib import Adapter
from transactron.utils import ModuleConnector, RecordIntDict
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, SimpleTestCircuit, TestGen
from transactron.utils.dependencies import DependencyContext

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
        self.flush_io = TestbenchIO(Adapter())

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

    def as_dict(self) -> dict[str, int]:
        return {"parity": self.parity, "ptr": self.ptr}


@dataclass(frozen=True)
class BPURequest:
    pc: int
    ftq_idx: FTQIndex
    global_branch_history: int
    bpu_stage: int


@dataclass(frozen=True)
class BlockPrediction:
    branch_mask: int
    cfi_idx: int
    cfi_type: CfiType
    cfi_target: Optional[int]

    def as_dict(self) -> dict[str, int]:
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
    bpu_stage: int


@dataclass(frozen=True)
class IFUResponse:
    ftq_idx: FTQIndex
    redirect: bool
    stall: bool
    block_prediction: BlockPrediction


@parameterized_class(
    ("name", "fetch_block_log"),
    [
        ("block4B", 2),
    ],
)
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
                start_pc=self.start_pc, ftq_size_log=self.ftq_size_log, fetch_block_bytes_log=self.fetch_block_log
            )
        )

        # Override directly in genparams
        self.gen_params.bpu_stages_cnt = bpu_stages_cnt

        self.bpu = MockBPU(self.gen_params)
        self.ftq = SimpleTestCircuit(FetchTargetQueue(self.gen_params, self.bpu))
        self.fetch_resume_mock = TestbenchIO(Adapter())
        DependencyContext.get().add_dependency(FetchResumeKey(), self.fetch_resume_mock.adapter.iface)

        self.m = ModuleConnector(self.bpu, self.ftq)

        self.expected_bpu_requests: Deque[tuple[BPURequest, list[tuple[int, int]], BlockPrediction]] = deque()
        self.bpu_target_resp: list[Optional[RecordIntDict]] = [None] * (self.bpu_stages_cnt + 1)
        self.bpu_details_resp: list[Optional[RecordIntDict]] = [None] * (self.bpu_stages_cnt + 1)

        self.expected_ifu_requests: Deque[tuple[IFURequest, IFUResponse]] = deque()

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
                pass

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

    @def_method_mock(lambda self: self.bpu.flush_io)
    def bpu_flush_mock(self):
        pass

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

    def expect_bpu_request(self, req: BPURequest, targets: list[tuple[int, int]], pred: BlockPrediction):
        assert len(targets) == self.bpu_stages_cnt
        self.expected_bpu_requests.append((req, targets, pred))

    def read_jump_target(self, ftq_idx: FTQIndex) -> TestGen[Optional[int]]:
        yield from self.ftq.jump_target_req.call(ftq_idx=ftq_idx.as_dict())
        ret = yield from self.ftq.jump_target_resp.call()
        return None if ~ret["maybe_cfi_target"]["valid"] else ret["maybe_cfi_target"]["value"]

    def expect_ifu_request(self, req: IFURequest, resp: IFUResponse):
        self.expected_ifu_requests.append((req, resp))

    def ifu_processes(self, latency: int):
        pipeline: list[Optional[tuple[int, IFUResponse]]] = [None] * (latency + 1)

        def input():
            yield Passive()
            while True:
                if len(self.expected_ifu_requests) == 0:
                    yield
                    continue

                req, resp = self.expected_ifu_requests.popleft()
                pipeline[latency] = (req.bpu_stage, resp)

                fetch_target = yield from self.ftq.consume_fetch_target.call()
                assert fetch_target["pc"] == req.pc
                assert fetch_target["ftq_idx"] == req.ftq_idx.as_dict()
                assert fetch_target["bpu_stage"] == req.bpu_stage

        def output():
            yield Passive()
            while True:
                yield Settle()
                resp = pipeline[0]
                for i in range(latency):
                    pipeline[i] = pipeline[i + 1]
                pipeline[latency] = None

                if resp is None:
                    yield
                    continue

                yield from self.ftq.consume_prediction.call_init(ftq_idx=resp[1].ftq_idx.as_dict(), bpu_stage=resp[0])
                yield Settle()
                res = yield from self.ftq.consume_prediction.call_result()
                assert res is not None

                if not res["discard"]:
                    yield from self.ftq.ifu_writeback.call(
                        ftq_idx=resp[1].ftq_idx.as_dict(),
                        redirect=resp[1].redirect,
                        stall=resp[1].stall,
                        block_prediction=resp[1].block_prediction.as_dict(),
                    )
                else:
                    yield
                yield from self.ftq.consume_prediction.disable()

        return (input, output)

    def test_simple_1stage_bpu(self):
        self.init_module(1)

        def test_proc():
            yield

            # Start with a simple case where we have no mispredictions whatsoever

            # Let's first
            for i in range(self.gen_params.ftq_size):
                self.expect_bpu_request(
                    BPURequest((i + 1) * 0x100, FTQIndex(i, False), i * 0x42, 0),
                    [((i + 2) * 0x100, (i + 1) * 0x42)],
                    BlockPrediction(0, 0, CfiType.INVALID, None),
                )
                self.expect_ifu_request(
                    IFURequest((i + 1) * 0x100, FTQIndex(i, False), 0),
                    IFUResponse(FTQIndex(i, False), False, False, BlockPrediction(0, 0, CfiType.INVALID, None)),
                )
            yield from self.tick(40)

        with self.run_simulation(self.m) as sim:
            ifu_in, ifu_out = self.ifu_processes(3)
            sim.add_sync_process(ifu_in)
            sim.add_sync_process(ifu_out)
            sim.add_sync_process(self.bpu_process)
            sim.add_sync_process(test_proc)
