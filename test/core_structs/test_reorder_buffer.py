import pytest
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rob import ReorderBuffer
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from queue import Queue
from random import Random, randrange

from transactron.testing.functions import data_const_to_dict


@pytest.mark.parametrize("mark_done_ports, frontend_superscalarity, retirement_superscalarity", [(1, 1, 1), (4, 4, 4)])
class TestReorderBuffer(TestCaseWithSimulator):
    async def gen_input(self, sim: TestbenchContext):
        for _ in range(self.test_steps):
            while self.regs_left_queue.empty():
                await sim.tick()

            await self.random_wait_geom(sim, 0.5)  # to slow down puts
            count = randrange(1, self.gen_params.frontend_superscalarity + 1)
            entries = []
            for k in range(count):
                log_reg = self.rand.randint(0, self.log_regs - 1)
                phys_reg = self.regs_left_queue.get()
                entries.append({"rl_dst": log_reg, "rp_dst": phys_reg, "tag_increment": 0})
            rob_ids = (await self.m.put.call(sim, count=count, entries=entries)).entries
            for k in range(count):
                self.to_execute_list.append((rob_ids[k].rob_id, entries[k]["rp_dst"]))
                self.retire_queue.put((entries[k], rob_ids[k].rob_id))

    def tb_do_updates(self, k: int):
        async def do_updates(sim: TestbenchContext):
            while True:
                await self.random_wait_geom(sim, 0.5)  # to slow down execution
                if len(self.to_execute_list) == 0:
                    await sim.tick()
                else:
                    idx = self.rand.randint(0, len(self.to_execute_list) - 1)
                    rob_id, executed = self.to_execute_list.pop(idx)
                    self.executed_list.append(executed)
                    await self.m.mark_done[k].call(sim, rob_id=rob_id, exception=0)

        return do_updates

    async def do_retire(self, sim: TestbenchContext):
        call_cnt = 0
        self.m.peek.call_init(sim)
        while True:
            if self.retire_queue.empty():
                res = await self.m.retire.call_try(sim)
                assert res is None  # transaction should not be ready if there is nothing to retire
            else:
                results = self.m.peek.get_call_result(sim)
                count = randrange(1, results.count + 1)
                regs, rob_id_exp = zip(*(self.retire_queue.get() for _ in range(count)))
                print(
                    regs,
                    rob_id_exp,
                    [(entry.rob_data.rl_dst, entry.rob_data.rp_dst, entry.rob_id) for entry in results.entries],
                )
                await self.m.retire.call(sim, count=count)
                for k in range(count):
                    phys_reg = results.entries[k].rob_data.rp_dst
                    assert rob_id_exp[k] == results.entries[k].rob_id
                    assert phys_reg in self.executed_list
                    self.executed_list.remove(phys_reg)

                    assert data_const_to_dict(results.entries[k].rob_data) == regs[k]
                    self.regs_left_queue.put(phys_reg)

                call_cnt += 1
                if self.test_steps == call_cnt:
                    break

    def test_single(self, mark_done_ports: int, frontend_superscalarity: int, retirement_superscalarity: int):
        self.rand = Random(0)
        self.test_steps = 2000
        self.gen_params = GenParams(
            test_core_config.replace(
                phys_regs_bits=5,
                rob_entries_bits=6,
                frontend_superscalarity=frontend_superscalarity,
                retirement_superscalarity=retirement_superscalarity,
            )
        )  # smaller size means better coverage
        m = SimpleTestCircuit(ReorderBuffer(self.gen_params, mark_done_ports=mark_done_ports))
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
            for k in range(mark_done_ports):
                sim.add_testbench(self.tb_do_updates(k), background=True)
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
        m = SimpleTestCircuit(ReorderBuffer(self.gen_params, mark_done_ports=1))
        self.m = m
        self.to_execute_list = []

        self.log_regs = self.gen_params.isa.reg_cnt
        self.phys_regs = 2**self.gen_params.phys_regs_bits

        with self.run_simulation(m) as sim:
            sim.add_testbench(self.gen_input)
            sim.add_testbench(self.do_retire)
