import random
import queue
from typing import Callable, Union
from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator, Settle
from coreblocks.transactions import TransactionModule, TransactionContext
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans, Adapter
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
            method_out = Adapter(o=layouts.rob_allocate_out, i=layouts.rob_allocate_out)
            m.submodules.rob_alloc = ROBAllocate(
                get_instr=rename_out_buf.read,
                push_instr=method_out.iface,
                rob_put=self.rob.put,
                gen_params=self.gen_params,
            )

            # mocked input and output
            m.submodules.output = self.out = TestbenchIO(method_out)
            m.submodules.rob_markdone = self.rob_done = TestbenchIO(AdapterTrans(self.rob.mark_done))
            m.submodules.rob_retire = self.rob_retire = TestbenchIO(AdapterTrans(self.rob.retire))
            m.submodules.instr_input = self.instr_inp = TestbenchIO(AdapterTrans(instr_fifo.write))
            m.submodules.free_rf_inp = self.free_rf_inp = TestbenchIO(AdapterTrans(free_rf_fifo.write))

        return tm


class TestRegAllocAndRename(TestCaseWithSimulator):
    def setUp(self):
        self.expected_rename_queue = queue.Queue()
        self.expected_phys_reg_queue = queue.Queue()
        self.free_regs_queue = queue.Queue()
        self.free_ROB_entries_queue = queue.Queue()
        self.current_RAT = [x for x in range(0, 32)]

        self.gen_params = GenParams()
        self.m = RegAllocAndRenameTestCircuit(self.gen_params)

        random.seed(42)
        for i in range(1, 2**self.gen_params.phys_regs_bits):
            self.free_phys_reg(i)

    def free_phys_reg(self, reg_id):
        self.free_regs_queue.put({"data": reg_id})
        self.expected_phys_reg_queue.put(reg_id)

    def make_queue_process(
        self,
        io: TestbenchIO,
        q: queue.Queue,
        after_call: Union[Callable[[dict, dict], None], None] = None,
        input_io=False,
    ):
        def queue_process():
            while True:
                try:
                    item = q.get_nowait()
                    # None signals to end the process
                    if item is None:
                        return
                    result = yield from io.call(item if input_io else {})
                    if after_call is not None:
                        yield Settle()
                        yield from after_call(result, item)
                except queue.Empty:
                    yield

        return queue_process

    def make_output_process(self):
        def after_call(got, expected):
            rlog_out = yield self.m.rob.data[got["rob_id"]].rob_data.rl_dst
            self.assertEqual(got["rphys_1"], expected["rphys_1"])
            self.assertEqual(got["rphys_2"], expected["rphys_2"])
            self.assertEqual(got["rphys_out"], expected["rphys_out"])
            self.assertEqual(rlog_out, expected["rlog_out"])

            # recycle physical register number
            if got["rphys_out"] != 0:
                self.free_phys_reg(got["rphys_out"])
            # recycle ROB entry
            self.free_ROB_entries_queue.put({"rob_id": got["rob_id"]})

        return self.make_queue_process(self.m.out, self.expected_rename_queue, after_call, input_io=False)

    def test_randomized(self):
        def instr_input_process():
            yield from self.m.rob_retire.enable()

            for i in range(500):
                rlog_1 = random.randint(0, 31)
                rlog_2 = random.randint(0, 31)
                rlog_out = random.randint(0, 31)
                rphys_1 = self.current_RAT[rlog_1]
                rphys_2 = self.current_RAT[rlog_2]
                rphys_out = self.expected_phys_reg_queue.get() if rlog_out != 0 else 0

                self.expected_rename_queue.put(
                    {"rphys_1": rphys_1, "rphys_2": rphys_2, "rlog_out": rlog_out, "rphys_out": rphys_out}
                )
                self.current_RAT[rlog_out] = rphys_out

                yield from self.m.instr_inp.call({"rlog_1": rlog_1, "rlog_2": rlog_2, "rlog_out": rlog_out})

            # Terminate other processes
            self.expected_rename_queue.put(None)
            self.free_regs_queue.put(None)
            self.free_ROB_entries_queue.put(None)

        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.make_output_process())
            sim.add_sync_process(self.make_queue_process(self.m.rob_done, self.free_ROB_entries_queue, input_io=True))
            sim.add_sync_process(self.make_queue_process(self.m.free_rf_inp, self.free_regs_queue, input_io=True))
            sim.add_sync_process(instr_input_process)
