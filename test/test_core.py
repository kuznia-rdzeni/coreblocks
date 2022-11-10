from typing import Iterable

from amaranth import Elaboratable, Module
from amaranth.sim import Settle

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.core import Core
from coreblocks.genparams import GenParams
from coreblocks.layouts import FetchLayouts
from coreblocks.wishbone import WishboneMaster, WishboneMemorySlave, WishboneParameters

import random
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
)
from riscvmodel.model import Model
from riscvmodel.isa import InstructionRType, get_insns
from riscvmodel.variant import RV32I


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams, instr_mem: Iterable[int] = None):
        self.gp = gen_params
        self.instr_mem = instr_mem

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        wb_params = WishboneParameters(data_width=32, addr_width=32)
        self.wb_master = WishboneMaster(wb_params=wb_params)
        self.wb_mem_slave = WishboneMemorySlave(wb_params=wb_params, width=32, depth=1024, init=self.instr_mem)
        self.core = Core(gen_params=self.gp, wb_master=self.wb_master)
        self.reg_feed_in = TestbenchIO(AdapterTrans(self.core.free_rf_fifo.write))
        self.io_in = TestbenchIO(AdapterTrans(self.core.fifo_fetch.write))
        self.rf_write = TestbenchIO(AdapterTrans(self.core.RF.write))
        self.reset = TestbenchIO(AdapterTrans(self.core.reset))

        m.submodules.wb_master = self.wb_master
        m.submodules.wb_mem_slave = self.wb_mem_slave
        m.submodules.reg_feed_in = self.reg_feed_in
        m.submodules.c = self.core
        m.submodules.io_in = self.io_in
        m.submodules.rf_write = self.rf_write
        m.submodules.reset = self.reset

        m.d.comb += self.wb_master.wbMaster.connect(self.wb_mem_slave.bus)

        return tm


def gen_riscv_add_instr(dst, src1, src2):
    return 0b0110011 | dst << 7 | src1 << 15 | src2 << 20


def gen_riscv_lui_instr(dst, imm):
    return 0b0110111 | dst << 7 | imm << 12


class TestCore(TestCaseWithSimulator):
    def reset_core(self):
        yield from self.m.reset.call()
        yield Settle()

    def check_RAT_alloc(self, rat, expected_alloc_count=None):
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
        yield from self.m.io_in.call({"data": opcode})

    def init_regs(self):
        for i in range(2**self.m.gp.phys_regs_bits - 1):
            yield from self.m.reg_feed_in.call({"data": i + 1})

    def run_test(self):
        # this test first provokes allocation of physical registers,
        # then sets the values in those registers, and finally runs
        # an actual computation.

        # The test sets values in the reg file by hand

        yield from self.init_regs()

        # provoking allocation of physical register
        for i in range(self.m.gp.isa.reg_cnt - 1):
            yield from self.push_instr(gen_riscv_add_instr(i + 1, 0, 0))

        # waiting for the retirement rat to be set
        for i in range(50):
            yield

        # checking if all registers have been allocated
        yield from self.check_RAT_alloc(self.m.core.FRAT, 31)
        yield from self.check_RAT_alloc(self.m.core.RRAT, 31)

        # writing values to physical registers
        yield from self.m.rf_write.call({"reg_id": (yield from self.get_phys_reg_rrat(1)), "reg_val": 1})
        yield from self.m.rf_write.call({"reg_id": (yield from self.get_phys_reg_rrat(2)), "reg_val": 2})
        yield from self.m.rf_write.call({"reg_id": (yield from self.get_phys_reg_rrat(3)), "reg_val": 3})

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
        gp = GenParams("rv32i", phys_regs_bits=6, rob_entries_bits=7)
        m = TestElaboratable(gp)
        self.m = m

        with self.runSimulation(m) as sim:
            sim.add_sync_process(self.run_test)

    def compare_core_states(self, sw_core):
        for i in range(self.gp.isa.reg_cnt):
            reg_val = sw_core.state.intreg.regs[i].value
            unsigned_val = reg_val if reg_val >= 0 else reg_val + 2**32
            self.assertEqual((yield from self.get_arch_reg_val(i)), unsigned_val)

    def randomized_input(self):
        instructions = get_insns(cls=InstructionRType)
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

        software_core = Model(RV32I)

        yield from self.init_regs()
        # allocate some random values for registers
        for i in range(self.gp.isa.reg_cnt):
            instr_init = InstructionADDI(rd=i, rs1=0, imm=random.randint(-(2**11), 2**11 - 1))
            software_core.execute(instr_init)
            yield from self.push_instr(instr_init.encode())

        for i in range(50):
            yield

        yield from self.compare_core_states(software_core)

        # generate random instruction stream
        for i in range(self.instr_count):
            instr = random.choice(instructions)()
            instr.randomize(RV32I)
            software_core.execute(instr)
            yield from self.push_instr(instr.encode())

        for i in range(50):
            yield

        yield from self.compare_core_states(software_core)

    def test_randomized(self):
        self.gp = GenParams("rv32i", phys_regs_bits=6, rob_entries_bits=7)
        m = TestElaboratable(self.gp)
        self.m = m
        self.instr_count = 300
        random.seed(42)

        with self.runSimulation(m) as sim:
            sim.add_sync_process(self.randomized_input)
