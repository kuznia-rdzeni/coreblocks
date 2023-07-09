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
            flush = self.rand.random() < 0.5
            rob_id = yield from self.m.put.call(regs)
            self.to_execute_list.append((rob_id, phys_reg, flush))
            self.retire_queue.put((regs, rob_id["rob_id"], flush))
            self.end_idx += 1

    def do_updates(self):
        yield Passive()
        while True:
            while self.rand.random() < 0.5:
                yield  # to slow down execution
            if len(self.to_execute_list) == 0:
                yield
            else:
                idx = self.rand.randint(0, len(self.to_execute_list) - 1)
                rob_id, executed, flush = self.to_execute_list.pop(idx)
                yield from self.m.mark_done.call(rob_id)
                if not flush:
                    self.executed_list.append(executed)

    def do_retire(self):
        while True:
            if self.retire_queue.empty():
                self.m.retire.enable()
                yield
                is_ready = yield self.m.retire.adapter.done
                self.assertEqual(is_ready, 0)  # transaction should not be ready if there is nothing to retire
            else:
                regs, rob_id_exp, flush = self.retire_queue.get()
                results = yield from self.m.peek.call()
                phys_reg = results["rob_data"]["rp_dst"]
                self.assertEqual(rob_id_exp, results["rob_id"])

                yield Settle()
                self.assertEqual(results["rob_data"], regs)
                self.regs_left_queue.put(phys_reg)

                if flush:
                    yield from self.m.flush_one.call()
                else:
                    yield from self.m.retire.call()
                    self.assertIn(phys_reg, self.executed_list)
                    self.executed_list.remove(phys_reg)

                self.start_idx += 1
                if self.test_steps == self.start_idx:
                    break

    def indices_process(self):
        yield Passive()
        while True:
            yield from self.m.get_indices.enable()
            yield from self.m.empty.enable()
            yield Settle()
            # make sure of the methods' nonexclusivity
            self.assertEqual((yield from self.m.get_indices.done()), 1)
            self.assertEqual((yield from self.m.empty.done()), 1)
            indices = yield from self.m.get_indices.get_outputs()
            is_empty = yield from self.m.empty.get_outputs()
            # maybe this shouldn't be checked since it's an implementation detail
            # but we're already leaking abstraction by allowing direct read access
            # to start_idx and end_idx
            self.assertEqual(indices["start"] == indices["end"], bool(is_empty["empty"]))
            rob_size = 2**self.gp.rob_entries_bits
            self.assertEqual(self.end_idx % rob_size, indices["end"])
            self.assertEqual(self.start_idx % rob_size, indices["start"])
            yield

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 2000
        self.gp = GenParams(
            test_core_config.replace(phys_regs_bits=5, rob_entries_bits=6)
        )  # smaller size means better coverage
        m = SimpleTestCircuit(ReorderBuffer(self.gp))
        self.m = m

        self.regs_left_queue = Queue()
        self.to_execute_list = []
        self.executed_list = []
        self.retire_queue = Queue()
        for i in range(2**self.gp.phys_regs_bits):
            self.regs_left_queue.put(i)
        self.end_idx = 0
        self.start_idx = 0

        self.log_regs = self.gp.isa.reg_cnt
        self.xlen = self.gp.isa.xlen

        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_updates)
            sim.add_sync_process(self.do_retire)
            sim.add_sync_process(self.indices_process)


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
