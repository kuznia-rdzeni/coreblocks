import random
import queue
from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator
from coreblocks.transactions import TransactionModule, TransactionContext
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans
from coreblocks.scheduler import RegAllocation, Renaming, RAT
from coreblocks.layouts import SchedulerLayouts
from coreblocks.genparams import GenParams
from .common import TestCaseWithSimulator

class RegAllocAndRenameTestCircuit(Elaboratable):
    def __init__(self, gen_params : GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        layouts = SchedulerLayouts(self.gen_params)
        instr_record = Record(layouts.instr_layout)

        with tm.transactionContext():
            m.submodules.instr_fifo = instr_fifo = FIFO(layouts.instr_layout, 16)
            m.submodules.free_rf_fifo = free_rf_fifo = FIFO(self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits)
            
            m.submodules.alloc_rename_buf = alloc_rename_buf = FIFO(layouts.reg_alloc_out, 2)
            m.submodules.reg_alloc = reg_alloc = RegAllocation(get_instr=instr_fifo.read,
                                                            push_instr=alloc_rename_buf.write,
                                                            get_free_reg=free_rf_fifo.read,
                                                            layouts=layouts,
                                                            gen_params=self.gen_params)

            m.submodules.rat = rat = RAT(layouts=layouts, gen_params=self.gen_params)
            m.submodules.rename_out_buf = rename_out_buf = FIFO(layouts.renaming_out, 2)
            m.submodules.renaming = renaming = Renaming(get_instr=alloc_rename_buf.read,
                                                        push_instr=rename_out_buf.write,
                                                        rename=rat.if_rename,
                                                        layouts=layouts,
                                                        gen_params=self.gen_params)

            # mocked input and output
            m.submodules.output = self.out = AdapterTrans(rename_out_buf.read, o=renaming.output_layout)
            m.submodules.instr_input = self.instr_inp = AdapterTrans(instr_fifo.write, i=layouts.instr_layout)
            m.submodules.free_rf_inp = self.free_rf_inp = AdapterTrans(free_rf_fifo.write, i=[('data', self.gen_params.phys_regs_bits)])

        return tm

class TestRegAllocAndRename(TestCaseWithSimulator):
    def setUp(self):
        self.expected_rename = queue.Queue()
        self.expected_phys_reg = queue.Queue()
        self.current_RAT = [x for x in range(0, 32)]
        self.recycled_regs = queue.Queue()
        self.gen_params = GenParams()
        self.m = RegAllocAndRenameTestCircuit(self.gen_params)

        random.seed(42)
        for i in range(1, 2**self.gen_params.phys_regs_bits):
            self.recycle_phys_reg(i)

    def check_renamed(self, rphys_1, rphys_2, rlog_out, rphys_out):
        self.assertEqual((yield self.m.out.data_out.rphys_1), rphys_1)
        self.assertEqual((yield self.m.out.data_out.rphys_2), rphys_2)
        self.assertEqual((yield self.m.out.data_out.rlog_out), rlog_out)
        self.assertEqual((yield self.m.out.data_out.rphys_out), rphys_out)

    def put_instr(self, rlog_1, rlog_2, rlog_out):
        yield (self.m.instr_inp.data_in.rlog_1.eq(rlog_1))
        yield (self.m.instr_inp.data_in.rlog_2.eq(rlog_2))
        yield (self.m.instr_inp.data_in.rlog_out.eq(rlog_out))
        yield
        while (yield self.m.instr_inp.done) != 1:
            yield

    def recycle_phys_reg(self, reg_id):
        self.recycled_regs.put(reg_id)
        self.expected_phys_reg.put(reg_id)

    def test_randomized(self):
        def bench_output():
            while True:
                try:
                    item = self.expected_rename.get_nowait()
                    if item is None:
                        yield self.m.out.en.eq(0)
                        return
                    yield self.m.out.en.eq(1)
                    yield
                    while (yield self.m.out.done) != 1:
                        yield
                    yield from self.check_renamed(**item)
                    yield self.m.out.en.eq(0)
                    # recycle physical register number
                    if item['rphys_out'] != 0:
                        self.recycle_phys_reg(item['rphys_out'])
                except queue.Empty:
                    yield

        def bench_instr_input():
            yield (self.m.instr_inp.en.eq(1))
            for i in range(500):
                rlog_1 = random.randint(0, 31)
                rlog_2 = random.randint(0, 31)
                rlog_out = random.randint(0, 31)
                rphys_1 = self.current_RAT[rlog_1]
                rphys_2 = self.current_RAT[rlog_2]
                rphys_out = self.expected_phys_reg.get() if rlog_out != 0 else 0

                self.expected_rename.put({'rphys_1': rphys_1, 'rphys_2': rphys_2, 'rlog_out': rlog_out, 'rphys_out': rphys_out})
                self.current_RAT[rlog_out] = rphys_out

                yield from self.put_instr(rlog_1, rlog_2, rlog_out)

            yield (self.m.instr_inp.en.eq(0))
            self.expected_rename.put(None)
            self.recycled_regs.put(None)
            
        def bench_free_rf_input():
            while True:
                try:
                    reg = self.recycled_regs.get_nowait()
                    if reg is None:
                        yield self.m.free_rf_inp.en.eq(0)
                        return
                    yield self.m.free_rf_inp.en.eq(1)
                    yield self.m.free_rf_inp.data_in.eq(reg)
                    yield
                    while (yield self.m.free_rf_inp.done) != 1:
                        yield
                    yield self.m.free_rf_inp.en.eq(0)
                except queue.Empty:
                    yield

        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(bench_output)
            sim.add_sync_process(bench_instr_input)
            sim.add_sync_process(bench_free_rf_input)