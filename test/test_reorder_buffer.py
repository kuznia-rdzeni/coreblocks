from amaranth import *
from amaranth.sim import *

from coreblocks.transactions.core import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.reorder_buffer import ReorderBuffer
from coreblocks.layouts import ROBLayouts
from coreblocks.genparams import GenParams

from queue import Queue
from random import Random


class TestElaboratable(Elaboratable):
    def elaborate(self, platform):
        gp = GenParams()
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            rb = ReorderBuffer(gp)

            self.io_in = TestbenchIO(AdapterTrans(rb.put))
            self.io_update = TestbenchIO(AdapterTrans(rb.mark_done))
            self.io_out = TestbenchIO(AdapterTrans(rb.retire))

            m.submodules.rb = rb
            m.submodules.io_in = self.io_in
            m.submodules.io_update = self.io_update
            m.submodules.io_out = self.io_out

        return tm


class TestReorderBuffer(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            if self.regs_left_queue.empty():
                yield
            else:
                log_reg = self.rand.randint(0, self.log_regs - 1)
                phys_reg = self.regs_left_queue.get()
                # print(log_reg, phys_reg)
                regs = {"rl_dst": log_reg, "rp_dst": phys_reg}
                rob_id = yield from self.m.io_in.call(regs)
                self.to_execute_list.append((rob_id, phys_reg))
                self.retire_queue.put(regs)

    def do_updates(self):
        yield Passive()
        while True:
            yield  # yield to slow down execution
            if len(self.to_execute_list) == 0:
                yield
            else:
                idx = self.rand.randint(0, len(self.to_execute_list) - 1)
                rob_id, executed = self.to_execute_list.pop(idx)
                self.executed_list.append(executed)
                yield from self.m.io_update.call(rob_id)

    def do_retire(self):
        cnt = 0
        while True:
            if self.retire_queue.empty():
                yield
            else:
                regs = self.retire_queue.get()
                results = yield from self.m.io_out.call()
                # print(results)
                phys_reg = results["rp_dst"]
                assert phys_reg in self.executed_list
                self.executed_list.remove(phys_reg)
                # print(self.executed_list)
                self.assertEqual(results, regs)
                self.regs_left_queue.put(phys_reg)

                cnt += 1
                if self.test_steps == cnt:
                    break

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 1000
        m = TestElaboratable()
        self.m = m

        self.regs_left_queue = Queue()
        self.to_execute_list = []
        self.executed_list = []
        self.retire_queue = Queue()
        gp = GenParams()
        for i in range(2**gp.phys_regs_bits):
            self.regs_left_queue.put(i)

        self.log_regs = 2**gp.log_regs_bits

        with self.runSimulation(m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_updates)
            sim.add_sync_process(self.do_retire)
