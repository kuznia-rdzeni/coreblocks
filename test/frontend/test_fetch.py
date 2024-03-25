from collections import deque
from parameterized import parameterized_class
import random

from riscvmodel.insn import InstructionJAL, InstructionBEQ

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

    def add_instr(self, data: int, jumps: bool, jump_offset: int = 0, branch_taken: bool = False):
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

        print(f"adding instr pc=0x{self.pc:x} 0x{data:x}, rvc: {rvc}, jumps: {jumps}, next_pc: {next_pc:x}")

        self.pc = next_pc

    def gen_non_branch_instr(self, rvc: bool):
        if rvc:
            data = (random.randrange(2**11) << 2) | 0b01
        else:
            data = random.randrange(2**32) & ~0b1111111
            data |= 0b11  # 2 lowest bits must be set in 32-bit long instructions

        self.add_instr(data, False)

    def gen_jal(self, offset: int, rvc: bool = False):
        if rvc:
            data = 0x2025
        else:
            data = InstructionJAL(rd=0, imm=offset).encode()
            # data = JTypeInstr.encode(opcode=Opcode.JAL, rd=0, imm=offset)
            # assert data == data2

        self.add_instr(data, True, jump_offset=offset, branch_taken=True)

    def gen_branch(self, offset: int, taken: bool):
        data = InstructionBEQ(rs1=0, rs2=0, imm=offset).encode()
        # data = BTypeInstr.encode(opcode=Opcode.BRANCH, imm=offset, funct3=Funct3.BEQ, rs1=0, rs2=0)
        # assert data == data2

        self.add_instr(data, True, jump_offset=offset, branch_taken=taken)

    def gen_random_instr_seq(self, count: int):
        pc = self.gen_params.start_pc

        for _ in range(count):
            is_branch = random.random() < 0.15
            is_rvc = random.random() < 0.5
            branch_target = random.randrange(2**self.gen_params.isa.ilen) & ~0b1

            error = random.random() < 0.1
            error = False
            is_branch = False

            if is_rvc:
                data = (random.randrange(2**11) << 2) | 0b01  # C.ADDI
                if is_branch:
                    data = data | (0b101 << 13)  # make it C.J

                self.mem[pc] = data
                if error:
                    self.memerr.add(pc)
            else:
                data = random.randrange(2**self.gen_params.isa.ilen) & ~0b1111111
                data |= 0b11  # 2 lowest bits must be set in 32-bit long instructions
                if is_branch:
                    data |= 0b1100000
                    data &= ~0b0010000

                self.mem[pc] = data & 0xFFFF
                self.mem[pc + 2] = data >> 16
                if error:
                    self.memerr.add(random.choice([pc, pc + 2]))

            next_pc = pc + (2 if is_rvc else 4)
            if is_branch:
                next_pc = branch_target

            self.instr_queue.append(
                {
                    "pc": pc,
                    "is_branch": is_branch,
                    "next_pc": next_pc,
                    "rvc": is_rvc,
                }
            )

            pc = next_pc

    def cache_process(self):
        yield Passive()

        while True:
            while len(self.input_q) == 0:
                yield

            while random.random() < 0.5:
                yield

            req_addr = self.input_q.popleft() & ~(self.gen_params.fetch_block_bytes - 1)

            def load_or_gen_mem(addr):
                return self.mem[addr] if addr in self.mem else random.randrange(2**16)

            fetch_block = 0
            bad_addr = False
            for i in range(0, self.gen_params.fetch_block_bytes, 2):
                fetch_block |= load_or_gen_mem(req_addr + i) << (8 * i)
                if req_addr + i in self.memerr:
                    bad_addr = True

            print(f"Cache process request: 0x{req_addr:x} error:{bad_addr}, block={fetch_block:x}")

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

            print(f"fetch out {instr['pc']:x}", instr["branch_taken"])

            instr_error = (instr["pc"] & (~0b11)) in self.memerr or (instr["pc"] & (~0b11)) + 2 in self.memerr
            if instr["pc"] & 2 and not instr["rvc"]:
                instr_error |= ((instr["pc"] + 2) & (~0b11)) in self.memerr or (
                    (instr["pc"] + 2) & (~0b11)
                ) + 2 in self.memerr

            v = yield from self.io_out.call()

            self.assertEqual(v["pc"], instr["pc"])
            self.assertEqual(v["access_fault"], instr_error)

            instr_data = instr["instr"]
            if (instr_data & 0b11) == 0b11:
                self.assertEqual(v["instr"], instr_data)

            if (instr["jumps"] and (instr["branch_taken"] != v["predicted_taken"])) or instr_error:
                print("redirecting!!!!", v["predicted_taken"])
                yield from self.random_wait(5)
                yield from self.fetch_stall_exception.call()
                yield from self.random_wait(5)
                print("about to clean")

                # Empty the pipeline
                yield from self.clean_fifo.call_try()
                yield

                print("cleaned")

                # Resume the fetch unit
                while (yield from self.fetch_resume.call_try(pc=instr["next_pc"], resume_from_exception=1)) is None:
                    pass

                print("resumed")

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
        block_pc = self.pc
        self.gen_jal(self.gen_params.fetch_block_bytes)
        for i in range(self.gen_params.fetch_block_bytes // 4 - 1):
            data = InstructionJAL(rd=0, imm=-8).encode()
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

        self.gen_jal(40, rvc=True)

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

    def _test_random(self):
        self.gen_random_instr_seq(20)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.cache_process)
            sim.add_sync_process(self.fetch_out_check)
