from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans, FIFO

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.core import Core
from coreblocks.genparams import GenParams
from coreblocks.layouts import FetchLayouts

from queue import Queue
from random import Random


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.fifo_in = FIFO(self.gp.get(FetchLayouts).raw_instr, 2)
        self.core = Core(gen_params=self.gp, get_raw_instr=self.fifo_in.read)
        self.reg_feed_in = TestbenchIO(AdapterTrans(self.core.put_reg))
        self.io_in = TestbenchIO(AdapterTrans(self.fifo_in.write))

        m.submodules.fifo_in = self.fifo_in
        m.submodules.reg_feed_in = self.reg_feed_in
        m.submodules.c = self.core
        m.submodules.io_in = self.io_in

        return tm

def gen_riscv_add_instr(dst, src1, src2):
    return 0b0110011 | dst << 7 | src1 << 15 | src2 << 20


class TestCore(TestCaseWithSimulator):
    def run_test(self):

        # this test first provokes allocation of physical registers, 
        # then sets the values in those registers, and finally runs 
        # an actual computation.

        # The test sets values in the reg file by hand, 
        # as I am not sure if we support OpImm instructions or not.

        for i in range(2**self.m.gp.phys_regs_bits - 1):
            yield from self.m.reg_feed_in.call({"reg":i+1})

        # provoking allocation of physical register
        for i in range(self.m.gp.isa.reg_cnt - 1):
            yield from self.m.io_in.call({"data": gen_riscv_add_instr(i+1, 0, 0)})

        # waiting for the retirement rat to be set
        for i in range(100):
            yield

        for i in range(self.m.gp.isa.reg_cnt):
            print("f", i, (yield self.m.core.FRAT.entries[i]))

        for i in range(self.m.gp.isa.reg_cnt):
            print("r", i, (yield self.m.core.RRAT.entries[i]))
        
        # writing values to physical registers
        yield self.m.core.RF.entries[(yield self.m.core.RRAT.entries[1])].reg_val.eq(1)
        yield self.m.core.RF.entries[(yield self.m.core.RRAT.entries[2])].reg_val.eq(2)
        yield self.m.core.RF.entries[(yield self.m.core.RRAT.entries[3])].reg_val.eq(3)

        for i in range(self.m.gp.isa.reg_cnt):
            print(i, (yield self.m.core.RF.entries[(yield self.m.core.RRAT.entries[i])].reg_val))

        # issuing actual instructions for the test
        yield from self.m.io_in.call({"data": gen_riscv_add_instr(4, 1, 2)})
        yield from self.m.io_in.call({"data": gen_riscv_add_instr(4, 3, 4)})

        # waiting for the instructions to be processed
        for i in range(100):
            yield

        for i in range(self.m.gp.isa.reg_cnt):
            print(i, (yield self.m.core.RF.entries[(yield self.m.core.RRAT.entries[i])].reg_val))

        for i in range(10):
            print((yield self.m.core.RRAT.entries[i]))

        # 1 + 2 + 3 = 6
        self.assertEqual((yield self.m.core.RF.entries[(yield self.m.core.RRAT.entries[4])].reg_val), 6)

    def test_single(self):
        gp = GenParams("rv32i", phys_regs_bits=5, rob_entries_bits=6)
        m = TestElaboratable(gp)
        self.m = m

        self.regs_left_queue = Queue()
        self.to_execute_list = []
        self.executed_list = []
        self.retire_queue = Queue()
        for i in range(2**gp.phys_regs_bits):
            self.regs_left_queue.put(i)

        self.log_regs = 2**gp.isa.xlen_log

        with self.runSimulation(m) as sim:
            sim.add_sync_process(self.run_test)

