from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rob import ReorderBuffer
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from queue import Queue
from random import Random

from transactron.testing.functions import data_const_to_dict


class TestReorderBuffer(TestCaseWithSimulator):
    async def gen_input(self, sim: TestbenchContext):
        for _ in range(self.test_steps):
            while self.regs_left_queue.empty():
                await sim.tick()

            await self.random_wait_geom(sim, 0.5)  # to slow down puts
            log_reg = self.rand.randint(0, self.log_regs - 1)
            phys_reg = self.regs_left_queue.get()
            regs = {"rl_dst": log_reg, "rp_dst": phys_reg, "tag_increment": 0}
            rob_id = (await self.m.put.call(sim, regs)).rob_id
            self.to_execute_list.append((rob_id, phys_reg))
            self.retire_queue.put((regs, rob_id))

    async def do_updates(self, sim: TestbenchContext):
        while True:
            await self.random_wait_geom(sim, 0.5)  # to slow down execution
            if len(self.to_execute_list) == 0:
                await sim.tick()
            else:
                idx = self.rand.randint(0, len(self.to_execute_list) - 1)
                rob_id, executed = self.to_execute_list.pop(idx)
                self.executed_list.append(executed)
                await self.m.mark_done.call(sim, rob_id=rob_id, exception=0)

    async def do_retire(self, sim: TestbenchContext):
        cnt = 0
        while True:
            if self.retire_queue.empty():
                res = await self.m.retire.call_try(sim)
                assert res is None  # transaction should not be ready if there is nothing to retire
            else:
                regs, rob_id_exp = self.retire_queue.get()
                results = await self.m.peek.call(sim)
                await self.m.retire.call(sim)
                phys_reg = results.rob_data.rp_dst
                assert rob_id_exp == results.rob_id
                assert phys_reg in self.executed_list
                self.executed_list.remove(phys_reg)

                assert data_const_to_dict(results.rob_data) == regs
                self.regs_left_queue.put(phys_reg)

                cnt += 1
                if self.test_steps == cnt:
                    break

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 2000
        self.gen_params = GenParams(
            test_core_config.replace(phys_regs_bits=5, rob_entries_bits=6)
        )  # smaller size means better coverage
        m = SimpleTestCircuit(ReorderBuffer(self.gen_params))
        self.m = m

        self.regs_left_queue = Queue()
        self.to_execute_list = []
        self.executed_list = []
        self.retire_queue = Queue()
        for i in range(2**self.gen_params.phys_regs_bits):
            self.regs_left_queue.put(i)

        self.log_regs = self.gen_params.isa.reg_cnt

        with self.run_simulation(m) as sim:
            sim.add_testbench(self.gen_input)
            sim.add_testbench(self.do_updates, background=True)
            sim.add_testbench(self.do_retire)


class TestFullDoneCase(TestCaseWithSimulator):
    async def gen_input(self, sim: TestbenchContext):
        for _ in range(self.test_steps):
            log_reg = self.rand.randrange(self.log_regs)
            phys_reg = self.rand.randrange(self.phys_regs)
            rob_id = (await self.m.put.call(sim, rl_dst=log_reg, rp_dst=phys_reg)).rob_id
            self.to_execute_list.append(rob_id)

    async def do_single_update(self, sim: TestbenchContext):
        while len(self.to_execute_list) == 0:
            await sim.tick()

        rob_id = self.to_execute_list.pop(0)
        await self.m.mark_done.call(sim, rob_id=rob_id)

    async def do_retire(self, sim: TestbenchContext):
        for i in range(self.test_steps - 1):
            await self.do_single_update(sim)

        await self.m.retire.call(sim)
        await self.do_single_update(sim)

        for i in range(self.test_steps - 1):
            await self.m.retire.call(sim)

        res = await self.m.retire.call_try(sim)
        assert res is None  # since we have read all elements

    def test_single(self):
        self.rand = Random(0)

        self.gen_params = GenParams(test_core_config)
        self.test_steps = 2**self.gen_params.rob_entries_bits
        m = SimpleTestCircuit(ReorderBuffer(self.gen_params))
        self.m = m
        self.to_execute_list = []

        self.log_regs = self.gen_params.isa.reg_cnt
        self.phys_regs = 2**self.gen_params.phys_regs_bits

        with self.run_simulation(m) as sim:
            sim.add_testbench(self.gen_input)
            sim.add_testbench(self.do_retire)
