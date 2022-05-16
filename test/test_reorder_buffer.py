from amaranth import *
from amaranth.sim import *

from coreblocks.transactions.core import TransactionModule

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.reorder_buffer import ReorderBuffer, in_layout, id_layout

from queue import Queue
from random import randint, seed


class TestElaboratable(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)
        with tm.transactionContext():
            rb = ReorderBuffer()
            self.io_in = TestbenchIO(rb.put, i=in_layout, o=id_layout)
            self.io_update = TestbenchIO(rb.mark_done, i=id_layout)
            self.io_out = TestbenchIO(rb.retire, o=in_layout)

            m.submodules.rb = rb
            m.submodules.io_in = self.io_in
            m.submodules.io_update = self.io_update
            m.submodules.io_out = self.io_out

        return tm


class TestReorderBuffer(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(1000):
            if self.regs_left_queue.empty():
                yield
            else:
                log_reg = randint(0, 31)
                phys_reg = self.regs_left_queue.get()
                # print(log_reg, phys_reg)
                regs = {"dst_reg": log_reg, "phys_dst_reg": phys_reg}
                rob_id = yield from self.m.io_in.putget(regs)
                self.execute_list.append(rob_id)
                self.retire_queue.put(regs)

    def do_updates(self):
        yield Passive()
        while True:
            if len(self.execute_list) == 0:
                yield
            else:
                idx = randint(0, len(self.execute_list) - 1)
                rob_id = self.execute_list.pop(idx)
                yield from self.m.io_update.put(rob_id)

    def do_retire(self):
        yield Passive()
        while True:
            if self.retire_queue.empty():
                yield
            else:
                regs = self.retire_queue.get()
                results = yield from self.m.io_out.get()
                # print(results)
                self.assertEqual(results["dst_reg"], regs["dst_reg"])
                self.assertEqual(results["phys_dst_reg"], regs["phys_dst_reg"])
                self.regs_left_queue.put(regs["phys_dst_reg"])

    def test_single(self):
        # print("running")
        m = TestElaboratable()
        self.m = m

        self.regs_left_queue = Queue()
        self.execute_list = []
        self.retire_queue = Queue()

        for i in range(128):
            self.regs_left_queue.put(i)

        seed(0)
        with self.runSimulation(m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_updates)
            sim.add_sync_process(self.do_retire)
