import pytest
from typing import Optional
from dataclasses import dataclass
from parameterized import parameterized_class
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestGen

from coreblocks.frontend.fetch.fetch import PredictionChecker
from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config

"""
import pytest
from typing import Optional
from collections import deque
from dataclasses import dataclass
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive
from coreblocks.interface.keys import FetchResumeKey

from transactron.core import Method
from transactron.lib import AdapterTrans, Adapter, BasicFifo
from transactron.utils import ModuleConnector
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, SimpleTestCircuit, TestGen

from coreblocks.frontend.fetch.fetch import FetchUnit, PredictionChecker
from coreblocks.cache.iface import CacheInterface
from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.interface.layouts import ICacheLayouts, FetchLayouts
from transactron.utils.dependencies import DependencyContext

class MockedICache(Elaboratable, CacheInterface):
    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(ICacheLayouts)

        self.issue_req_io = TestbenchIO(Adapter(i=layouts.issue_req))
        self.accept_res_io = TestbenchIO(Adapter(o=layouts.accept_res))

        self.issue_req = self.issue_req_io.adapter.iface
        self.accept_res = self.accept_res_io.adapter.iface
        self.flush = Method()

    def elaborate(self, platform):
        m = Module()

        m.submodules.issue_req_io = self.issue_req_io
        m.submodules.accept_res_io = self.accept_res_io

        return m


@parameterized_class(
    ("name", "fetch_block_log", "with_rvc"),
    [
        ("block4B", 2, False),
        ("block4B_rvc", 2, True),
        ("block8B", 3, False),
        ("block8B_rvc", 3, True),
        ("block16B", 4, False),
        ("block16B_rvc", 4, True),
    ],
)
class TestFetchUnit(TestCaseWithSimulator):
    fetch_block_log: int
    with_rvc: bool

    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.pc = 0
        self.gen_params = GenParams(
            test_core_config.replace(
                start_pc=self.pc, compressed=self.with_rvc, fetch_block_bytes_log=self.fetch_block_log
            )
        )

        self.icache = MockedICache(self.gen_params)
        fifo = BasicFifo(self.gen_params.get(FetchLayouts).raw_instr, depth=2)
        self.io_out = TestbenchIO(AdapterTrans(fifo.read))
        self.clean_fifo = TestbenchIO(AdapterTrans(fifo.clear))
        self.fetch_resume_mock = TestbenchIO(Adapter())
        DependencyContext.get().add_dependency(FetchResumeKey(), self.fetch_resume_mock.adapter.iface)

        self.fetch = SimpleTestCircuit(FetchUnit(self.gen_params, self.icache, fifo.write))

        self.m = ModuleConnector(self.icache, fifo, self.io_out, self.clean_fifo, self.fetch)

        self.instr_queue = deque()
        self.mem = {}
        self.memerr = set()
        self.input_q = deque()
        self.output_q = deque()

        random.seed(41)

    def add_instr(self, data: int, jumps: bool, jump_offset: int = 0, branch_taken: bool = False) -> int:
        rvc = (data & 0b11) != 0b11
        if rvc:
            self.mem[self.pc] = data
        else:
            self.mem[self.pc] = data & 0xFFFF
            self.mem[self.pc + 2] = data >> 16

        next_pc = self.pc + (2 if rvc else 4)
        if jumps and branch_taken:
            next_pc = self.pc + jump_offset

        self.instr_queue.append(
            {
                "instr": data,
                "pc": self.pc,
                "jumps": jumps,
                "branch_taken": branch_taken,
                "next_pc": next_pc,
                "rvc": rvc,
            }
        )

        instr_pc = self.pc
        self.pc = next_pc

        return instr_pc

    def gen_non_branch_instr(self, rvc: bool) -> int:
        if rvc:
            data = (random.randrange(2**11) << 2) | 0b01
        else:
            data = random.randrange(2**32) & ~0b1111111
            data |= 0b11  # 2 lowest bits must be set in 32-bit long instructions

        return self.add_instr(data, False)

    def gen_jal(self, offset: int) -> int:
        data = JTypeInstr(opcode=Opcode.JAL, rd=0, imm=offset).encode()

        return self.add_instr(data, True, jump_offset=offset, branch_taken=True)

    def gen_branch(self, offset: int, taken: bool):
        data = BTypeInstr(opcode=Opcode.BRANCH, imm=offset, funct3=Funct3.BEQ, rs1=0, rs2=0).encode()

        return self.add_instr(data, True, jump_offset=offset, branch_taken=taken)

    def cache_process(self):
        yield Passive()

        while True:
            while len(self.input_q) == 0:
                yield

            while random.random() < 0.5:
                yield

            req_addr = self.input_q.popleft() & ~(self.gen_params.fetch_block_bytes - 1)

            def load_or_gen_mem(addr):
                if addr in self.mem:
                    return self.mem[addr]

                # Make sure to generate a compressed instruction to avoid
                # random cross boundary instructions.
                return random.randrange(2**16) & ~(0b11)

            fetch_block = 0
            bad_addr = False
            for i in range(0, self.gen_params.fetch_block_bytes, 2):
                fetch_block |= load_or_gen_mem(req_addr + i) << (8 * i)
                if req_addr + i in self.memerr:
                    bad_addr = True

            self.output_q.append({"fetch_block": fetch_block, "error": bad_addr})

    @def_method_mock(lambda self: self.icache.issue_req_io, enable=lambda self: len(self.input_q) < 2, sched_prio=1)
    def issue_req_mock(self, addr):
        self.input_q.append(addr)

    @def_method_mock(lambda self: self.icache.accept_res_io, enable=lambda self: len(self.output_q) > 0)
    def accept_res_mock(self):
        return self.output_q.popleft()

    def fetch_out_check(self):
        while self.instr_queue:
            instr = self.instr_queue.popleft()

            access_fault = instr["pc"] in self.memerr
            if not instr["rvc"]:
                access_fault |= instr["pc"] + 2 in self.memerr

            v = yield from self.io_out.call()

            assert v["pc"] == instr["pc"]
            assert v["access_fault"] == access_fault

            instr_data = instr["instr"]
            if (instr_data & 0b11) == 0b11:
                assert v["instr"] == instr_data

            if (instr["jumps"] and (instr["branch_taken"] != v["predicted_taken"])) or access_fault:
                yield from self.random_wait(5)
                yield from self.fetch.stall_exception.call()
                yield from self.random_wait(5)

                # Empty the pipeline
                yield from self.clean_fifo.call_try()
                yield

                resume_pc = instr["next_pc"]
                if access_fault:
                    # Resume from the next fetch block
                    resume_pc = (
                        instr["pc"] & ~(self.gen_params.fetch_block_bytes - 1)
                    ) + self.gen_params.fetch_block_bytes

                # Resume the fetch unit
                while (yield from self.fetch.resume_from_exception.call_try(pc=resume_pc)) is None:
                    pass

    def run_sim(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.cache_process)
            sim.add_sync_process(self.fetch_out_check)

    def test_simple_no_jumps(self):
        for _ in range(50):
            self.gen_non_branch_instr(rvc=False)

        self.run_sim()

    def test_simple_no_jumps_rvc(self):
        if not self.with_rvc:
            self.run_sim()  # Run simulation to avoid unused warnings.
            return

        # Try a fetch block full of non-RVC instructions
        for _ in range(self.gen_params.fetch_width // 2):
            self.gen_non_branch_instr(rvc=False)

        # Try a fetch block full of RVC instructions
        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=True)

        # Try what if an instruction crossed a boundary of a fetch block
        self.gen_non_branch_instr(rvc=True)
        for _ in range(self.gen_params.fetch_width - 1):
            self.gen_non_branch_instr(rvc=False)

        self.gen_non_branch_instr(rvc=True)

        # We are now at the beginning of a fetch block again.

        # RVC interleaved with non-RVC
        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=True)
            self.gen_non_branch_instr(rvc=False)

        # Random sequence
        for _ in range(50):
            self.gen_non_branch_instr(rvc=random.randrange(2) == 1)

        self.run_sim()

    def test_jumps(self):
        # Jump to the next instruction
        self.gen_jal(4)
        for _ in range(self.gen_params.fetch_block_bytes // 4 - 1):
            self.gen_non_branch_instr(rvc=False)

        # Jump to the next fetch block
        self.gen_jal(self.gen_params.fetch_block_bytes)

        # Two fetch blocks-worth of instructions
        for _ in range(self.gen_params.fetch_block_bytes // 2):
            self.gen_non_branch_instr(rvc=False)

        # Jump to the next fetch block, but fill the block with other jump instructions
        block_pc = self.gen_jal(self.gen_params.fetch_block_bytes)
        for i in range(self.gen_params.fetch_block_bytes // 4 - 1):
            data = JTypeInstr(opcode=Opcode.JAL, rd=0, imm=-8).encode()
            self.mem[block_pc + (i + 1) * 4] = data & 0xFFFF
            self.mem[block_pc + (i + 1) * 4 + 2] = data >> 16

        # Jump to the last instruction of a fetch block
        self.gen_jal(2 * self.gen_params.fetch_block_bytes - 4)

        self.gen_non_branch_instr(rvc=False)

        # Jump as the last instruction of the fetch block
        for _ in range(self.gen_params.fetch_block_bytes // 4 - 1):
            self.gen_non_branch_instr(rvc=False)
        self.gen_jal(20)

        # A chain of jumps
        for _ in range(10):
            self.gen_jal(random.randrange(4, 100, 4))

        # A big jump
        self.gen_jal(1000)
        self.gen_non_branch_instr(rvc=False)

        # And a jump backwards
        self.gen_jal(-200)
        for _ in range(5):
            self.gen_non_branch_instr(rvc=False)

        self.run_sim()

    def test_jumps_rvc(self):
        if not self.with_rvc:
            self.run_sim()
            return

        # Jump to the last instruction of a fetch block
        self.gen_jal(2 * self.gen_params.fetch_block_bytes - 2)
        self.gen_non_branch_instr(rvc=True)

        # Again, but the last instruction spans two fetch blocks
        self.gen_jal(2 * self.gen_params.fetch_block_bytes - 2)
        self.gen_non_branch_instr(rvc=False)

        for _ in range(self.gen_params.fetch_width - 1):
            self.gen_non_branch_instr(rvc=True)

        # Make a jump instruction that spans two fetch blocks
        for _ in range(self.gen_params.fetch_width - 1):
            self.gen_non_branch_instr(rvc=True)
        self.gen_jal(self.gen_params.fetch_block_bytes + 2)

        self.gen_non_branch_instr(rvc=False)

        self.run_sim()

    def test_branches(self):
        # Taken branch forward
        self.gen_branch(offset=self.gen_params.fetch_block_bytes, taken=True)

        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=False)

        # Not taken branch forward
        self.gen_branch(offset=self.gen_params.fetch_block_bytes, taken=False)

        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=False)

        # Jump somewhere far - biggest possible value
        self.gen_branch(offset=4092, taken=True)

        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=False)

        # Chain a few branches
        for i in range(10):
            self.gen_branch(offset=1028, taken=(i % 2 == 0))

        self.gen_non_branch_instr(rvc=False)

        self.run_sim()

    def test_access_fault(self):
        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=False)

        # Access fault at the beginning of the fetch block
        pc = self.gen_non_branch_instr(rvc=False)
        self.memerr.add(pc)

        # We will resume from the next fetch block
        self.pc = pc + self.gen_params.fetch_block_bytes

        for _ in range(self.gen_params.fetch_width):
            self.gen_non_branch_instr(rvc=False)

        # Access fault in a block with a jump
        pc = self.gen_jal(2 * self.gen_params.fetch_block_bytes)
        self.memerr.add(pc)

        # We will resume from the next fetch block
        self.pc = pc + self.gen_params.fetch_block_bytes

        self.gen_non_branch_instr(rvc=False)

        self.run_sim()

    def test_random(self):
        for _ in range(500):
            r = random.random()
            if r < 0.6:
                rvc = random.randrange(2) == 0 if self.with_rvc else False
                self.gen_non_branch_instr(rvc=rvc)
            else:
                offset = random.randrange(0, 1000, 2)
                if not self.with_rvc:
                    offset = offset & ~(0b11)
                if r < 0.8:
                    self.gen_jal(offset)
                else:
                    self.gen_branch(offset, taken=random.randrange(2) == 0)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.cache_process)
            sim.add_sync_process(self.fetch_out_check)
"""


@dataclass(frozen=True)
class CheckerResult:
    mispredicted: bool
    target_valid: bool
    fb_instr_idx: int
    redirect_target: int


@parameterized_class(
    ("name", "fetch_block_log", "with_rvc"),
    [
        ("block4B", 2, False),
        ("block4B_rvc", 2, True),
        ("block8B", 3, False),
        ("block8B_rvc", 3, True),
        ("block16B", 4, False),
        ("block16B_rvc", 4, True),
    ],
)
class TestPredictionChecker(TestCaseWithSimulator):
    fetch_block_log: int
    with_rvc: bool

    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.gen_params = GenParams(
            test_core_config.replace(compressed=self.with_rvc, fetch_block_bytes_log=self.fetch_block_log)
        )

        self.m = SimpleTestCircuit(PredictionChecker(self.gen_params))

    def check(
        self,
        pc: int,
        block_cross: bool,
        predecoded: list[tuple[CfiType, int]],
        branch_mask: int,
        cfi_idx: int,
        cfi_type: CfiType,
        cfi_target: Optional[int],
        valid_mask: int = -1,
    ) -> TestGen[CheckerResult]:
        # Fill the array with non-CFI instructions
        for _ in range(self.gen_params.fetch_width - len(predecoded)):
            predecoded.append((CfiType.INVALID, 0))
        predecoded_raw = [
            {"cfi_type": predecoded[i][0], "cfi_offset": predecoded[i][1], "unsafe": 0}
            for i in range(self.gen_params.fetch_width)
        ]

        prediction = {
            "branch_mask": branch_mask,
            "cfi_idx": cfi_idx,
            "cfi_type": cfi_type,
            "cfi_target": cfi_target or 0,
            "cfi_target_valid": 1 if cfi_target is not None else 0,
        }

        instr_start = (
            pc & ((1 << self.gen_params.fetch_block_bytes_log) - 1)
        ) >> self.gen_params.min_instr_width_bytes_log

        instr_valid = (((1 << self.gen_params.fetch_width) - 1) << instr_start) & valid_mask

        res = yield from self.m.check.call(
            fb_addr=pc >> self.gen_params.fetch_block_bytes_log,
            instr_block_cross=block_cross,
            instr_valid=instr_valid,
            predecoded=predecoded_raw,
            prediction=prediction,
        )

        return CheckerResult(
            mispredicted=bool(res["mispredicted"]),
            target_valid=bool(res["target_valid"]),
            fb_instr_idx=res["fb_instr_idx"],
            redirect_target=res["redirect_target"],
        )

    def assert_resp(
        self,
        res: CheckerResult,
        mispredicted: Optional[bool] = None,
        target_valid: Optional[bool] = None,
        fb_instr_idx: Optional[int] = None,
        redirect_target: Optional[int] = None,
    ):
        if mispredicted is not None:
            assert res.mispredicted == mispredicted
        if target_valid is not None:
            assert res.target_valid == target_valid
        if fb_instr_idx is not None:
            assert res.fb_instr_idx == fb_instr_idx
        if redirect_target is not None:
            assert res.redirect_target == redirect_target

    def test_no_misprediction(self):
        instr_width = self.gen_params.min_instr_width_bytes
        fetch_width = self.gen_params.fetch_width

        def proc():
            # No CFI at all
            ret = yield from self.check(0x100, False, [], 0, 0, CfiType.INVALID, None)
            self.assert_resp(ret, mispredicted=False)

            # There is one forward branch that we didn't predict
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, 100)], 0, 0, CfiType.INVALID, None)
            self.assert_resp(ret, mispredicted=False)

            # There are many forward branches that we didn't predict
            ret = yield from self.check(
                0x100, False, [(CfiType.BRANCH, 100)] * fetch_width, 0, 0, CfiType.INVALID, None
            )
            self.assert_resp(ret, mispredicted=False)

            # There is a predicted JAL instr
            ret = yield from self.check(0x100, False, [(CfiType.JAL, 100)], 0, 0, CfiType.JAL, 0x100 + 100)
            self.assert_resp(ret, mispredicted=False)

            # There is a predicted JALR instr - the predecoded offset can now be anything
            ret = yield from self.check(0x100, False, [(CfiType.JALR, 200)], 0, 0, CfiType.JALR, 0x100 + 100)
            self.assert_resp(ret, mispredicted=False)

            # There is a forward taken-predicted branch
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, 100)], 0b1, 0, CfiType.BRANCH, 0x100 + 100)
            self.assert_resp(ret, mispredicted=False)

            # There is a backward taken-predicted branch
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, -100)], 0b1, 0, CfiType.BRANCH, 0x100 - 100)
            self.assert_resp(ret, mispredicted=False)

            # Branch located between two fetch blocks
            if self.with_rvc:
                ret = yield from self.check(
                    0x100, True, [(CfiType.BRANCH, -100)], 0b1, 0, CfiType.BRANCH, 0x100 - 100 - 2
                )
                self.assert_resp(ret, mispredicted=False)

            # One branch predicted as not taken
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, -100)], 0b1, 0, CfiType.INVALID, 0)
            self.assert_resp(ret, mispredicted=False)

            # Now tests for fetch blocks with multiple instructions
            if fetch_width < 2:
                return

            # Predicted taken branch as the second instruction
            ret = yield from self.check(
                0x100,
                False,
                [(CfiType.INVALID, 0), (CfiType.BRANCH, -100)],
                0b10,
                1,
                CfiType.BRANCH,
                0x100 + instr_width - 100,
            )
            self.assert_resp(ret, mispredicted=False)

            # Predicted, but not taken branch as the second instruction
            ret = yield from self.check(
                0x100, False, [(CfiType.INVALID, 0), (CfiType.BRANCH, -100)], 0b10, 0, CfiType.INVALID, 0
            )
            self.assert_resp(ret, mispredicted=False)

            if self.with_rvc:
                ret = yield from self.check(
                    0x100,
                    True,
                    [(CfiType.INVALID, 0), (CfiType.BRANCH, -100)],
                    0b10,
                    1,
                    CfiType.BRANCH,
                    0x100 + instr_width - 100,
                )
                self.assert_resp(ret, mispredicted=False)

                ret = yield from self.check(
                    0x100,
                    True,
                    [(CfiType.JAL, 100), (CfiType.JAL, -100)],
                    0b00,
                    1,
                    CfiType.JAL,
                    0x100 + instr_width - 100,
                    valid_mask=0b10,
                )
                self.assert_resp(ret, mispredicted=False)

            # Two branches with all possible combintations taken/not-taken
            ret = yield from self.check(
                0x100, False, [(CfiType.BRANCH, -100), (CfiType.BRANCH, 100)], 0b11, 0, CfiType.INVALID, 0
            )
            self.assert_resp(ret, mispredicted=False)
            ret = yield from self.check(
                0x100, False, [(CfiType.BRANCH, -100), (CfiType.BRANCH, 100)], 0b11, 0, CfiType.BRANCH, 0x100 - 100
            )
            self.assert_resp(ret, mispredicted=False)
            ret = yield from self.check(
                0x100,
                False,
                [(CfiType.BRANCH, -100), (CfiType.BRANCH, 100)],
                0b11,
                1,
                CfiType.BRANCH,
                0x100 + instr_width + 100,
            )
            self.assert_resp(ret, mispredicted=False)

            # JAL at the beginning, but we start from the second instruction
            ret = yield from self.check(0x100 + instr_width, False, [(CfiType.JAL, -100)], 0b0, 0, CfiType.INVALID, 0)
            self.assert_resp(ret, mispredicted=False)

            # JAL and a forward branch that we didn't predict
            ret = yield from self.check(
                0x100 + instr_width, False, [(CfiType.JAL, -100), (CfiType.BRANCH, 100)], 0b00, 0, CfiType.INVALID, 0
            )
            self.assert_resp(ret, mispredicted=False)

            # two JAL instructions, but we start from the second one
            ret = yield from self.check(
                0x100 + instr_width,
                False,
                [(CfiType.JAL, -100), (CfiType.JAL, 100)],
                0b00,
                1,
                CfiType.JAL,
                0x100 + instr_width + 100,
            )
            self.assert_resp(ret, mispredicted=False)

            # JAL and a branch, but we start from the second instruction
            ret = yield from self.check(
                0x100 + instr_width,
                False,
                [(CfiType.JAL, -100), (CfiType.BRANCH, 100)],
                0b10,
                1,
                CfiType.BRANCH,
                0x100 + instr_width + 100,
            )
            self.assert_resp(ret, mispredicted=False)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(proc)

    def test_preceding_redirection(self):
        instr_width = self.gen_params.min_instr_width_bytes
        fetch_width = self.gen_params.fetch_width

        def proc():
            # No prediction was made, but there is a JAL at the beginning
            ret = yield from self.check(0x100, False, [(CfiType.JAL, 0x20)], 0, 0, CfiType.INVALID, None)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 + 0x20)

            # The same, but the jump is between two fetch blocks
            if self.with_rvc:
                ret = yield from self.check(0x100, True, [(CfiType.JAL, 0x20)], 0, 0, CfiType.INVALID, None)
                self.assert_resp(
                    ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 + 0x20 - 2
                )

            # Not predicted backward branch
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, -100)], 0b0, 0, CfiType.INVALID, 0)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 - 100)

            # Now tests for fetch blocks with multiple instructions
            if fetch_width < 2:
                return

            # We predicted the branch on the second instruction, but there's a JAL on the first one.
            ret = yield from self.check(
                0x100,
                False,
                [(CfiType.JAL, -100), (CfiType.BRANCH, 100)],
                0b10,
                1,
                CfiType.BRANCH,
                0x100 + instr_width + 100,
            )
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 - 100)

            # We predicted the branch on the second instruction, but there's a JALR on the first one.
            ret = yield from self.check(
                0x100,
                False,
                [(CfiType.JALR, -100), (CfiType.BRANCH, 100)],
                0b10,
                1,
                CfiType.BRANCH,
                0x100 + instr_width + 100,
            )
            self.assert_resp(ret, mispredicted=True, target_valid=False, fb_instr_idx=0)

            # We predicted the branch on the second instruction, but there's a backward on the first one.
            ret = yield from self.check(
                0x100,
                False,
                [(CfiType.BRANCH, -100), (CfiType.BRANCH, 100)],
                0b10,
                1,
                CfiType.BRANCH,
                0x100 + instr_width + 100,
            )
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 - 100)

            # Unpredicted backward branch as the second instruction
            ret = yield from self.check(
                0x100, False, [(CfiType.INVALID, 0), (CfiType.BRANCH, -100)], 0b00, 0, CfiType.INVALID, 0
            )
            self.assert_resp(
                ret, mispredicted=True, target_valid=True, fb_instr_idx=1, redirect_target=0x100 + instr_width - 100
            )

            # Unpredicted JAL as the second instruction
            ret = yield from self.check(
                0x100, False, [(CfiType.INVALID, 0), (CfiType.JAL, 100)], 0b00, 0, CfiType.INVALID, 0
            )
            self.assert_resp(
                ret, mispredicted=True, target_valid=True, fb_instr_idx=1, redirect_target=0x100 + instr_width + 100
            )

            # Unpredicted JALR as the second instruction
            ret = yield from self.check(
                0x100, False, [(CfiType.INVALID, 0), (CfiType.JALR, 100)], 0b00, 0, CfiType.INVALID, 0
            )
            self.assert_resp(ret, mispredicted=True, target_valid=False, fb_instr_idx=1)

            if fetch_width < 3:
                return

            ret = yield from self.check(
                0x100 + instr_width,
                False,
                [(CfiType.JAL, -100), (CfiType.INVALID, 100), (CfiType.JAL, 100)],
                0b0,
                0,
                CfiType.INVALID,
                None,
            )
            self.assert_resp(
                ret, mispredicted=True, target_valid=True, fb_instr_idx=2, redirect_target=0x100 + 2 * instr_width + 100
            )

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(proc)

    def test_mispredicted_cfi_type(self):
        instr_width = self.gen_params.min_instr_width_bytes
        fetch_width = self.gen_params.fetch_width
        fb_bytes = self.gen_params.fetch_block_bytes

        def proc():
            # We predicted a JAL, but in fact there is a non-CFI instruction
            ret = yield from self.check(0x100, False, [(CfiType.INVALID, 0)], 0, 0, CfiType.JAL, 100)
            self.assert_resp(
                ret,
                mispredicted=True,
                target_valid=True,
                fb_instr_idx=fetch_width - 1,
                redirect_target=0x100 + fb_bytes,
            )

            # We predicted a JAL, but in fact there is a branch
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, -100)], 0, 0, CfiType.JAL, 100)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 - 100)

            # We predicted a JAL, but in fact there is a JALR instruction
            ret = yield from self.check(0x100, False, [(CfiType.JALR, -100)], 0, 0, CfiType.JAL, 100)
            self.assert_resp(ret, mispredicted=True, target_valid=False, fb_instr_idx=0)

            # We predicted a branch, but in fact there is a JAL
            ret = yield from self.check(0x100, False, [(CfiType.JAL, -100)], 0b1, 0, CfiType.BRANCH, 100)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 - 100)

            if fetch_width < 2:
                return

            # There is a branch and a non-CFI, but we predicted two branches
            ret = yield from self.check(
                0x100, False, [(CfiType.BRANCH, -100), (CfiType.INVALID, 0)], 0b11, 1, CfiType.BRANCH, 100
            )
            self.assert_resp(
                ret,
                mispredicted=True,
                target_valid=True,
                fb_instr_idx=fetch_width - 1,
                redirect_target=0x100 + fb_bytes,
            )

            # The same as above, but we start from the second instruction
            ret = yield from self.check(
                0x100 + instr_width, False, [(CfiType.BRANCH, -100), (CfiType.INVALID, 0)], 0b11, 1, CfiType.BRANCH, 100
            )
            self.assert_resp(
                ret,
                mispredicted=True,
                target_valid=True,
                fb_instr_idx=fetch_width - 1,
                redirect_target=0x100 + fb_bytes,
            )

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(proc)

    def test_mispredicted_cfi_target(self):
        instr_width = self.gen_params.min_instr_width_bytes
        fetch_width = self.gen_params.fetch_width

        def proc():
            # We predicted a wrong JAL target
            ret = yield from self.check(0x100, False, [(CfiType.JAL, 100)], 0, 0, CfiType.JAL, 200)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 + 100)

            # We predicted a wrong branch target
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, 100)], 0b1, 0, CfiType.BRANCH, 200)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 + 100)

            # We didn't provide the branch target
            ret = yield from self.check(0x100, False, [(CfiType.BRANCH, 100)], 0b1, 0, CfiType.BRANCH, None)
            self.assert_resp(ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 + 100)

            # We predicted a wrong JAL target that is between two fetch blocks
            if self.with_rvc:
                ret = yield from self.check(0x100, True, [(CfiType.JAL, 100)], 0, 0, CfiType.JAL, 300)
                self.assert_resp(
                    ret, mispredicted=True, target_valid=True, fb_instr_idx=0, redirect_target=0x100 + 100 - 2
                )

            if fetch_width < 2:
                return

            # The second instruction is a branch without the target
            ret = yield from self.check(
                0x100, False, [(CfiType.INVALID, 0), (CfiType.BRANCH, 100)], 0b10, 1, CfiType.BRANCH, None
            )
            self.assert_resp(
                ret, mispredicted=True, target_valid=True, fb_instr_idx=1, redirect_target=0x100 + instr_width + 100
            )

            # The second instruction is a JAL with a wrong target
            ret = yield from self.check(
                0x100, False, [(CfiType.INVALID, 0), (CfiType.JAL, 100)], 0b10, 1, CfiType.JAL, 200
            )
            self.assert_resp(
                ret, mispredicted=True, target_valid=True, fb_instr_idx=1, redirect_target=0x100 + instr_width + 100
            )

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(proc)
