from amaranth.sim import Passive, Settle

from ..common import TestCaseWithSimulator, SimpleTestCircuit

from coreblocks.structs_common.rob import ReorderBuffer
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from queue import Queue
from random import Random


class TestReorderBuffer(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            while self.regs_left_queue.empty():
                yield

            while self.rand.random() < 0.5:
                yield  # to slow down puts
            log_reg = self.rand.randrange(0, self.log_regs)
            phys_reg = self.regs_left_queue.get()
            pc = self.rand.randrange(0, 2**self.xlen)
            regs = {"rl_dst": log_reg, "rp_dst": phys_reg, "pc": pc}
            rob_id = yield from self.m.put.call(regs)
            self.to_execute_list.append((rob_id, phys_reg))
            self.retire_queue.put((regs, rob_id["rob_id"]))

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
                yield from self.m.mark_done.call(rob_id)

    def do_retire(self):
        cnt = 0
        while True:
            if self.retire_queue.empty():
                self.m.retire.enable()
                yield
                is_ready = yield self.m.retire.adapter.done
                self.assertEqual(is_ready, 0)  # transaction should not be ready if there is nothing to retire
            else:
                regs, rob_id_exp = self.retire_queue.get()
                results = yield from self.m.peek.call()
                yield from self.m.retire.call()
                phys_reg = results["rob_data"]["rp_dst"]
                self.assertEqual(rob_id_exp, results["rob_id"])
                self.assertIn(phys_reg, self.executed_list)
                self.executed_list.remove(phys_reg)

                yield Settle()
                self.assertEqual(results["rob_data"], regs)
                self.regs_left_queue.put(phys_reg)

                cnt += 1
                if self.test_steps == cnt:
                    break

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 2000
        gp = GenParams(
            test_core_config.replace(phys_regs_bits=5, rob_entries_bits=6)
        )  # smaller size means better coverage
        m = SimpleTestCircuit(ReorderBuffer(gp))
        self.m = m

        self.regs_left_queue = Queue()
        self.to_execute_list = []
        self.executed_list = []
        self.retire_queue = Queue()
        for i in range(2**gp.phys_regs_bits):
            self.regs_left_queue.put(i)

        self.log_regs = gp.isa.reg_cnt
        self.xlen = gp.isa.xlen

        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_updates)
            sim.add_sync_process(self.do_retire)


class TestFullDoneCase(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            log_reg = self.rand.randrange(self.log_regs)
            phys_reg = self.rand.randrange(self.phys_regs)
            rob_id = yield from self.m.put.call(rl_dst=log_reg, rp_dst=phys_reg)
            self.to_execute_list.append(rob_id)

    def do_single_update(self):
        while len(self.to_execute_list) == 0:
            yield

        rob_id = self.to_execute_list.pop(0)
        yield from self.m.mark_done.call(rob_id)

    def do_retire(self):
        for i in range(self.test_steps - 1):
            yield from self.do_single_update()

        yield from self.m.retire.call()
        yield from self.do_single_update()

        for i in range(self.test_steps - 1):
            yield from self.m.retire.call()

        yield from self.m.retire.enable()
        yield
        res = yield self.m.retire.adapter.done
        self.assertEqual(res, 0)  # should be disabled, since we have read all elements

    def test_single(self):
        self.rand = Random(0)

        gp = GenParams(test_core_config)
        self.test_steps = 2**gp.rob_entries_bits
        m = SimpleTestCircuit(ReorderBuffer(gp))
        self.m = m
        self.to_execute_list = []

        self.log_regs = gp.isa.reg_cnt
        self.phys_regs = 2**gp.phys_regs_bits

        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_retire)
