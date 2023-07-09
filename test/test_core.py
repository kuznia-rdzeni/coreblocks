from amaranth import Elaboratable, Module

from transactron.lib import AdapterTrans
from coreblocks.utils import align_to_power_of_two

from .common import TestCaseWithSimulator, TestbenchIO, signed_to_int

from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.params.configurations import (
    CoreConfiguration,
    basic_core_config,
    full_core_config,
    interrupt_core_config,
)
from coreblocks.peripherals.wishbone import WishboneBus, WishboneMemorySlave

from typing import Optional, cast
import random
import subprocess
import tempfile
from parameterized import parameterized_class
from riscvmodel.insn import (
    InstructionADDI,
    InstructionSLTI,
    InstructionSLTIU,
    InstructionXORI,
    InstructionORI,
    InstructionANDI,
    InstructionSLLI,
    InstructionSRLI,
    InstructionSRAI,
    InstructionLUI,
    InstructionJAL,
)
from riscvmodel.model import Model
from riscvmodel.isa import Instruction, InstructionRType, get_insns
from riscvmodel.variant import RV32I


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams, instr_mem: list[int] = [0], data_mem: Optional[list[int]] = None):
        self.gp = gen_params
        self.instr_mem = instr_mem
        if data_mem is None:
            self.data_mem = [0] * (2**10)
        else:
            self.data_mem = data_mem

    def elaborate(self, platform):
        m = Module()

        wb_instr_bus = WishboneBus(self.gp.wb_params)
        wb_data_bus = WishboneBus(self.gp.wb_params)

        # Align the size of the memory to the length of a cache line.
        instr_mem_depth = align_to_power_of_two(len(self.instr_mem), self.gp.icache_params.block_size_bits)
        self.wb_mem_slave = WishboneMemorySlave(
            wb_params=self.gp.wb_params, width=32, depth=instr_mem_depth, init=self.instr_mem
        )
        self.wb_mem_slave_data = WishboneMemorySlave(
            wb_params=self.gp.wb_params, width=32, depth=len(self.data_mem), init=self.data_mem
        )
        self.core = Core(gen_params=self.gp, wb_instr_bus=wb_instr_bus, wb_data_bus=wb_data_bus)
        self.io_in = TestbenchIO(AdapterTrans(self.core.fifo_fetch.write))
        self.rf_write = TestbenchIO(AdapterTrans(self.core.RF.write))
        self.interrupt = TestbenchIO(AdapterTrans(self.core.int_coordinator.trigger))

        m.submodules.wb_mem_slave = self.wb_mem_slave
        m.submodules.wb_mem_slave_data = self.wb_mem_slave_data
        m.submodules.c = self.core
        m.submodules.io_in = self.io_in
        m.submodules.rf_write = self.rf_write
        m.submodules.interrupt = self.interrupt

        m.d.comb += wb_instr_bus.connect(self.wb_mem_slave.bus)
        m.d.comb += wb_data_bus.connect(self.wb_mem_slave_data.bus)

        return m


def gen_riscv_add_instr(dst, src1, src2):
    return 0b0110011 | dst << 7 | src1 << 15 | src2 << 20


def gen_riscv_lui_instr(dst, imm):
    return 0b0110111 | dst << 7 | imm << 12


class TestCoreBase(TestCaseWithSimulator):
    gp: GenParams
    m: TestElaboratable

    def check_RAT_alloc(self, rat, expected_alloc_count=None):  # noqa: N802
        allocated = []
        for i in range(self.m.gp.isa.reg_cnt):
            allocated.append((yield rat.entries[i]))
        filtered_zeros = list(filter(lambda x: x != 0, allocated))

        # check if 0th register is set to 0
        self.assertEqual(allocated[0], 0)
        # check if there are no duplicate physical registers allocated for two different architectural registers
        self.assertEqual(len(filtered_zeros), len(set(filtered_zeros)))
        # check if the expected number of allocated registers matches reality
        if expected_alloc_count:
            self.assertEqual(len(filtered_zeros), expected_alloc_count)

    def get_phys_reg_rrat(self, reg_id):
        return (yield self.m.core.RRAT.entries[reg_id])

    def get_phys_reg_frat(self, reg_id):
        return (yield self.m.core.FRAT.entries[reg_id])

    def get_arch_reg_val(self, reg_id):
        return (yield self.m.core.RF.entries[(yield from self.get_phys_reg_rrat(reg_id))].reg_val)

    def get_phys_reg_val(self, reg_id):
        return (yield self.m.core.RF.entries[reg_id].reg_val)

    def push_instr(self, opcode):
        yield from self.m.io_in.call(data=opcode)

    def push_arch_reg_val(self, reg_id, val):
        addi_imm = signed_to_int(val & 0xFFF, 12)
        lui_imm = (val & 0xFFFFF000) >> 12
        # handle addi sign extension, see: https://stackoverflow.com/a/59546567
        if val & 0x800:
            lui_imm = (lui_imm + 1) & (0xFFFFF)

        yield from self.push_instr(InstructionLUI(reg_id, lui_imm).encode())
        yield from self.push_instr(InstructionADDI(reg_id, reg_id, addi_imm).encode())

    def compare_core_states(self, sw_core):
        for i in range(self.gp.isa.reg_cnt):
            reg_val = sw_core.state.intreg.regs[i].value
            unsigned_val = reg_val & 0xFFFFFFFF
            self.assertEqual((yield from self.get_arch_reg_val(i)), unsigned_val)


class TestCoreSimple(TestCoreBase):
    def simple_test(self):
        # this test first provokes allocation of physical registers,
        # then sets the values in those registers, and finally runs
        # an actual computation.

        # The test sets values in the reg file by hand

        # provoking allocation of physical register
        for i in range(self.m.gp.isa.reg_cnt - 1):
            yield from self.push_instr(gen_riscv_add_instr(i + 1, 0, 0))

        # waiting for the retirement rat to be set
        for i in range(100):
            yield

        # checking if all registers have been allocated
        yield from self.check_RAT_alloc(self.m.core.FRAT, 31)
        yield from self.check_RAT_alloc(self.m.core.RRAT, 31)

        # writing values to physical registers
        yield from self.m.rf_write.call(reg_id=(yield from self.get_phys_reg_rrat(1)), reg_val=1)
        yield from self.m.rf_write.call(reg_id=(yield from self.get_phys_reg_rrat(2)), reg_val=2)
        yield from self.m.rf_write.call(reg_id=(yield from self.get_phys_reg_rrat(3)), reg_val=3)

        # waiting for potential conflicts on rf_write
        for i in range(10):
            yield

        self.assertEqual((yield from self.get_arch_reg_val(1)), 1)
        self.assertEqual((yield from self.get_arch_reg_val(2)), 2)
        self.assertEqual((yield from self.get_arch_reg_val(3)), 3)

        # issuing actual instructions for the test
        yield from self.push_instr(gen_riscv_add_instr(4, 1, 2))
        yield from self.push_instr(gen_riscv_add_instr(4, 3, 4))
        yield from self.push_instr(gen_riscv_lui_instr(5, 1))

        # waiting for the instructions to be processed
        for i in range(50):
            yield

        self.assertEqual((yield from self.get_arch_reg_val(1)), 1)
        self.assertEqual((yield from self.get_arch_reg_val(2)), 2)
        self.assertEqual((yield from self.get_arch_reg_val(3)), 3)
        # 1 + 2 + 3 = 6
        self.assertEqual((yield from self.get_arch_reg_val(4)), 6)
        self.assertEqual((yield from self.get_arch_reg_val(5)), 1 << 12)

    def test_simple(self):
        gp = GenParams(basic_core_config)
        m = TestElaboratable(gp)
        self.m = m

        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.simple_test)


class TestCoreRandomized(TestCoreBase):
    def randomized_input(self):
        infloop_addr = (len(self.instr_mem) - 1) * 4
        # wait for PC to go past all instruction
        while (yield self.m.core.fetch.pc) != infloop_addr:
            yield

        # finish calculations
        yield from self.tick(50)

        yield from self.compare_core_states(self.software_core)

    def test_randomized(self):
        self.gp = GenParams(basic_core_config)
        self.instr_count = 300
        random.seed(42)

        # cast is there to avoid stubbing riscvmodel
        instructions = cast(list[type[Instruction]], get_insns(cls=InstructionRType, variant=RV32I))
        instructions += [
            InstructionADDI,
            InstructionSLTI,
            InstructionSLTIU,
            InstructionXORI,
            InstructionORI,
            InstructionANDI,
            InstructionSLLI,
            InstructionSRLI,
            InstructionSRAI,
            InstructionLUI,
        ]

        # allocate some random values for registers
        init_instr_list = list(
            InstructionADDI(rd=i, rs1=0, imm=random.randint(-(2**11), 2**11 - 1))
            for i in range(self.gp.isa.reg_cnt)
        )

        # generate random instruction stream
        instr_list = list(random.choice(instructions)() for _ in range(self.instr_count))
        for instr in instr_list:
            instr.randomize(RV32I)

        self.software_core = Model(RV32I)
        self.software_core.execute(init_instr_list)
        self.software_core.execute(instr_list)

        # We add JAL instruction at the end to effectively create a infinite loop at the end of the program.
        all_instr = init_instr_list + instr_list + [InstructionJAL(rd=0, imm=0)]

        self.instr_mem = list(map(lambda x: x.encode(), all_instr))

        m = TestElaboratable(self.gp, instr_mem=self.instr_mem)
        self.m = m

        with self.run_simulation(m, max_cycles=20 * self.instr_count) as sim:
            sim.add_sync_process(self.randomized_input)


class TestCoreAsmSourceBase(TestCoreBase):
    base_dir: str = "test/asm/"

    def prepare_source(self, filename):
        bin_src = []

        with tempfile.NamedTemporaryFile() as asm_tmp:
            subprocess.check_call(
                [
                    "riscv64-unknown-elf-as",
                    "-mabi=ilp32",
                    # Specified manually, because toolchains from most distributions don't support new extensioins
                    # and this test should be accessible locally.
                    "-march=rv32im_zicsr",
                    "-o",
                    asm_tmp.name,
                    TestCoreAsmSourceBase.base_dir + filename,
                ]
            )
            code = subprocess.check_output(
                ["riscv64-unknown-elf-objcopy", "-O", "binary", "-j", ".text", asm_tmp.name, "/dev/stdout"]
            )
            for word_idx in range(0, len(code), 4):
                word = code[word_idx : word_idx + 4]
                bin_instr = int.from_bytes(word, "little")
                bin_src.append(bin_instr)
        return bin_src


@parameterized_class(
    ("name", "source_file", "cycle_count", "expected_regvals", "configuration"),
    [
        ("fibonacci", "fibonacci.asm", 1200, {2: 2971215073}, basic_core_config),
        ("fibonacci_mem", "fibonacci_mem.asm", 1500, {3: 55}, basic_core_config),
        ("csr", "csr.asm", 200, {1: 1, 2: 4}, full_core_config),
    ],
)
class TestCoreBasicAsmSource(TestCoreAsmSourceBase):
    source_file: str
    cycle_count: int
    expected_regvals: dict[int, int]
    configuration: CoreConfiguration

    def setUp(self):
        self.gp = GenParams(self.configuration)

    def run_and_check(self):
        yield from self.tick(self.cycle_count)
        for reg_id, val in self.expected_regvals.items():
            self.assertEqual((yield from self.get_arch_reg_val(reg_id)), val)

    def test_asm_source(self):
        bin_src = self.prepare_source(self.source_file)
        self.m = TestElaboratable(self.gp, instr_mem=bin_src)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.run_and_check)


# test interrupts with varying triggering frequency (parametrizable amount of cycles between
# returning from an interrupt and triggering it again with 'lo' and 'hi' parameters)
@parameterized_class(
    ("source_file", "main_cycle_count", "start_regvals", "expected_regvals", "lo", "hi"),
    [
        ("interrupt.asm", 800, {4: 2971215073, 8: 29}, {2: 2971215073, 7: 29, 31: 0xDE}, 300, 500),
        ("interrupt.asm", 800, {4: 24157817, 8: 199}, {2: 24157817, 7: 199, 31: 0xDE}, 100, 200),
        ("interrupt.asm", 400, {4: 89, 8: 843}, {2: 89, 7: 843, 31: 0xDE}, 30, 50),
        # 10-15 is the smallest feasible cycle count between interrupts to provide forward progress
        ("interrupt.asm", 300, {4: 21, 8: 9349}, {2: 21, 7: 9349, 31: 0xDE}, 10, 15),
    ],
)
class TestCoreInterrupt(TestCoreAsmSourceBase):
    source_file: str
    main_cycle_count: int
    start_regvals: dict[int, int]
    expected_regvals: dict[int, int]
    lo: int
    hi: int

    def setUp(self):
        self.configuration = interrupt_core_config
        self.gp = GenParams(self.configuration)
        random.seed(1500100900)

    def run_with_interrupt(self):
        main_cycles = 0
        int_count = 0

        # set up fibonacci max numbers
        for reg_id, val in self.start_regvals.items():
            yield from self.push_arch_reg_val(reg_id, val)
        # wait for caches to fill up so that mtvec is written - very important
        yield from self.tick(200)
        while main_cycles < self.main_cycle_count:
            # run main code for some semi-random amount of cycles
            c = random.randrange(self.lo, self.hi)
            main_cycles += c
            yield from self.tick(c)
            # trigger an interrupt
            yield from self.m.interrupt.call()
            # wait one clock cycle for the interrupt to get registered
            yield
            # wait until ISR returns
            while (yield self.m.core.int_coordinator.interrupt) != 0:
                yield
            int_count += 1

        self.assertEqual((yield from self.get_arch_reg_val(30)), int_count)
        for reg_id, val in self.expected_regvals.items():
            self.assertEqual((yield from self.get_arch_reg_val(reg_id)), val)

    def test_interrupted_prog(self):
        bin_src = self.prepare_source(self.source_file)
        self.m = TestElaboratable(self.gp, instr_mem=bin_src)
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.run_with_interrupt)
