import random
import queue
from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator
from coreblocks.transactions import TransactionModule, TransactionContext
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans
from coreblocks.scheduler import RegAllocation, Renaming, ROBAllocate, RAT
from coreblocks.layouts import SchedulerLayouts
from coreblocks.genparams import GenParams
from coreblocks.reorder_buffer import ReorderBuffer
from .common import TestCaseWithSimulator, TestbenchIO


class RegAllocAndRenameTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        layouts = SchedulerLayouts(self.gen_params)

        with tm.transactionContext():
            m.submodules.instr_fifo = instr_fifo = FIFO(layouts.instr_layout, 16)
            m.submodules.free_rf_fifo = free_rf_fifo = FIFO(
                self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits
            )

            m.submodules.alloc_rename_buf = alloc_rename_buf = FIFO(layouts.reg_alloc_out, 2)
            m.submodules.reg_alloc = RegAllocation(
                get_instr=instr_fifo.read,
                push_instr=alloc_rename_buf.write,
                get_free_reg=free_rf_fifo.read,
                gen_params=self.gen_params,
            )

            m.submodules.rat = rat = RAT(gen_params=self.gen_params)
            m.submodules.rename_out_buf = rename_out_buf = FIFO(layouts.renaming_out, 2)
            m.submodules.renaming = Renaming(
                get_instr=alloc_rename_buf.read,
                push_instr=rename_out_buf.write,
                rename=rat.if_rename,
                gen_params=self.gen_params,
            )

            m.submodules.rob = self.rob = ReorderBuffer(self.gen_params)
            m.submodules.rob_alloc_out_buf = rob_alloc_out_buf = FIFO(layouts.rob_allocate_out, 2)
            m.submodules.rob_alloc = ROBAllocate(
                get_instr=rename_out_buf.read,
                push_instr=rob_alloc_out_buf.write,
                rob_put=self.rob.put,
                gen_params=self.gen_params,
            )

            # mocked input and output
            m.submodules.output = self.out = TestbenchIO(AdapterTrans(rob_alloc_out_buf.read))
            m.submodules.rob_markdone = self.rob_done = TestbenchIO(AdapterTrans(self.rob.mark_done))
            m.submodules.rob_retire = self.rob_retire = TestbenchIO(AdapterTrans(self.rob.retire))
            m.submodules.instr_input = self.instr_inp = TestbenchIO(AdapterTrans(instr_fifo.write))
            m.submodules.free_rf_inp = self.free_rf_inp = TestbenchIO(AdapterTrans(free_rf_fifo.write))

        return tm


class TestRegAllocAndRename(TestCaseWithSimulator):
    def setUp(self):
        self.expected_rename = queue.Queue()
        self.expected_phys_reg = queue.Queue()
        self.current_RAT = [x for x in range(0, 32)]
        self.recycled_regs = queue.Queue()
        self.recycled_ROB_entries = queue.Queue()
        self.gen_params = GenParams()
        self.m = RegAllocAndRenameTestCircuit(self.gen_params)

        random.seed(42)
        for i in range(1, 2**self.gen_params.phys_regs_bits):
            self.recycle_phys_reg(i)

    def check_renamed(self, got, expected):
        self.assertEqual(got["rphys_1"], expected["rphys_1"])
        self.assertEqual(got["rphys_2"], expected["rphys_2"])
        self.assertEqual(got["rlog_out"], expected["rlog_out"])
        self.assertEqual(got["rphys_out"], expected["rphys_out"])

    def recycle_phys_reg(self, reg_id):
        self.recycled_regs.put(reg_id)
        self.expected_phys_reg.put(reg_id)

    def test_randomized(self):
        def bench_output():
            while True:
                try:
                    item = self.expected_rename.get_nowait()
                    if item is None:
                        return
                    result = yield from self.m.out.call()
                    result["rlog_out"] = yield self.m.rob.data[result["rob_id"]].rob_data.rl_dst

                    self.check_renamed(result, item)
                    # recycle physical register number
                    if item["rphys_out"] != 0:
                        self.recycle_phys_reg(item["rphys_out"])
                    # recycle ROB entry
                    self.recycled_ROB_entries.put(result["rob_id"])
                except queue.Empty:
                    yield

        def bench_instr_input():
            for i in range(500):
                rlog_1 = random.randint(0, 31)
                rlog_2 = random.randint(0, 31)
                rlog_out = random.randint(0, 31)
                rphys_1 = self.current_RAT[rlog_1]
                rphys_2 = self.current_RAT[rlog_2]
                rphys_out = self.expected_phys_reg.get() if rlog_out != 0 else 0

                self.expected_rename.put(
                    {"rphys_1": rphys_1, "rphys_2": rphys_2, "rlog_out": rlog_out, "rphys_out": rphys_out}
                )
                self.current_RAT[rlog_out] = rphys_out

                yield from self.m.instr_inp.call({"rlog_1": rlog_1, "rlog_2": rlog_2, "rlog_out": rlog_out})

            self.expected_rename.put(None)
            self.recycled_regs.put(None)
            self.recycled_ROB_entries.put(None)

        def bench_free_rf_input():
            while True:
                try:
                    reg = self.recycled_regs.get_nowait()
                    if reg is None:
                        return
                    yield from self.m.free_rf_inp.call({"data": reg})
                except queue.Empty:
                    yield

        def bench_rob_mark_done():
            while True:
                try:
                    entry = self.recycled_ROB_entries.get_nowait()
                    if entry is None:
                        return
                    yield from self.m.rob_done.call({"rob_id": entry})
                except queue.Empty:
                    yield

        def bench_rob_retire():
            yield from self.m.rob_retire.enable()

        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(bench_output)
            sim.add_sync_process(bench_instr_input)
            sim.add_sync_process(bench_free_rf_input)
            sim.add_sync_process(bench_rob_mark_done)
            sim.add_sync_process(bench_rob_retire)
