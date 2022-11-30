from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from ..common import TestCaseWithSimulator, TestbenchIO

from coreblocks.structs_common.rob import ReorderBuffer
from coreblocks.params import GenParams

from queue import Queue
from random import Random


class TestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gp = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)
        rb = ReorderBuffer(self.gp)

        self.rb = rb
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
            while self.regs_left_queue.empty():
                yield

            while self.rand.random() < 0.5:
                yield  # to slow down puts
            log_reg = self.rand.randint(0, self.log_regs - 1)
            phys_reg = self.regs_left_queue.get()
            regs = {"rl_dst": log_reg, "rp_dst": phys_reg}
            rob_id = yield from self.m.io_in.call(regs)
            self.to_execute_list.append((rob_id, phys_reg))
            self.retire_queue.put(regs)

    def do_updates(self):
        yield Passive()
        while True:
            while self.rand.random() < 0.5:
                yield  # to slow down execution
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
                self.m.io_out.enable()
                yield
                is_ready = yield self.m.io_out.adapter.done
                self.assertEqual(is_ready, 0)  # transaction should not be ready if there is nothing to retire
            else:
                regs = self.retire_queue.get()
                results = yield from self.m.io_out.call()
                phys_reg = results["rp_dst"]
                self.assertIn(phys_reg, self.executed_list)
                self.executed_list.remove(phys_reg)

                self.assertEqual(results, regs)
                self.regs_left_queue.put(phys_reg)

                cnt += 1
                if self.test_steps == cnt:
                    break

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 2000
        gp = GenParams("rv32i", phys_regs_bits=5, rob_entries_bits=6)  # smaller size means better coverage
        m = TestElaboratable(gp)
        self.m = m

        self.regs_left_queue = Queue()
        self.to_execute_list = []
        self.executed_list = []
        self.retire_queue = Queue()
        for i in range(2**gp.phys_regs_bits):
            self.regs_left_queue.put(i)

        self.log_regs = gp.isa.reg_cnt

        with self.runSimulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_updates)
            sim.add_sync_process(self.do_retire)


class TestFullDoneCase(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            log_reg = self.rand.randint(0, self.log_regs - 1)
            phys_reg = self.rand.randint(0, self.phys_regs - 1)
            regs = {"rl_dst": log_reg, "rp_dst": phys_reg}
            rob_id = yield from self.m.io_in.call(regs)
            self.to_execute_list.append(rob_id)

    def do_single_update(self):
        while len(self.to_execute_list) == 0:
            yield

        rob_id = self.to_execute_list.pop(0)
        yield from self.m.io_update.call(rob_id)

    def do_retire(self):
        for i in range(self.test_steps - 1):
            yield from self.do_single_update()

        yield from self.m.io_out.call()
        yield from self.do_single_update()

        for i in range(self.test_steps - 1):
            yield from self.m.io_out.call()

        yield from self.m.io_out.enable()
        yield
        res = yield self.m.io_out.adapter.done
        self.assertEqual(res, 0)  # should be disabled, since we have read all elements

    def test_single(self):
        self.rand = Random(0)

        gp = GenParams("rv32i")
        self.test_steps = 2**gp.rob_entries_bits
        m = TestElaboratable(gp)
        self.m = m
        self.to_execute_list = []

        self.log_regs = gp.isa.reg_cnt
        self.phys_regs = 2**gp.phys_regs_bits

        with self.runSimulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_retire)
