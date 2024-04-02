from collections import deque
from parameterized import parameterized_class
import random

from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from transactron.core import Method
from transactron.lib import AdapterTrans, Adapter, BasicFifo
from transactron.utils import ModuleConnector
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock

from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.cache.iface import CacheInterface
from coreblocks.frontend.decoder.isa import *
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.interface.layouts import ICacheLayouts, FetchLayouts


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

    def setUp(self) -> None:
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
        fetch = FetchUnit(self.gen_params, self.icache, fifo.write)
        self.fetch_resume = TestbenchIO(AdapterTrans(fetch.resume))
        self.fetch_stall_exception = TestbenchIO(AdapterTrans(fetch.stall_exception))

        self.m = ModuleConnector(
            self.icache, fifo, self.io_out, self.clean_fifo, fetch, self.fetch_resume, self.fetch_stall_exception
        )

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

            self.assertEqual(v["pc"], instr["pc"])
            self.assertEqual(v["access_fault"], access_fault)

            instr_data = instr["instr"]
            if (instr_data & 0b11) == 0b11:
                self.assertEqual(v["instr"], instr_data)

            if (instr["jumps"] and (instr["branch_taken"] != v["predicted_taken"])) or access_fault:
                yield from self.random_wait(5)
                yield from self.fetch_stall_exception.call()
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
                while (yield from self.fetch_resume.call_try(pc=resume_pc, resume_from_exception=1)) is None:
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
