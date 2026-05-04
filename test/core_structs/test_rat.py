from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rat import RRAT
from coreblocks.params import GenParams
from coreblocks.params import configurations

from collections import deque
from random import Random

import pytest


class TestRetirementRegisterAliasTable(TestCaseWithSimulator):
    async def clear_chosen(self, sim: TestbenchContext):
        while True:
            self.chosen = set()
            await sim.tick()

    def do_commit(self, i: int):
        async def tb(sim: TestbenchContext):
            # wait until R-RAT clears itself after reset
            await self.tick(sim, self.gen_params.isa.reg_cnt)
            for _ in range(self.test_steps):
                await sim.delay(1e-12 * i)
                rl = self.rand.choice(list(set(range(self.gen_params.isa.reg_cnt)) - self.chosen))
                rp = self.rand.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
                self.chosen.add(rl)

                if self.rand.randrange(2):
                    peek_res = await self.m.peek[i].call(sim, rl_dst=rl)
                    assert peek_res.old_rp_dst == self.expected_entries[rl]
                else:
                    res = await self.m.commit[i].call(sim, rl_dst=rl, rp_dst=rp)
                    assert res.old_rp_dst == self.expected_entries[rl]

                    self.expected_entries[rl] = rp

        return tb

    def test_single(self, ports: int):
        self.rand = Random(0)
        self.test_steps = 2000
        self.gen_params = GenParams(
            configurations.test.replace(phys_regs_bits=5, rob_entries_bits=6, retirement_superscalarity=ports)
        )
        m = SimpleTestCircuit(RRAT(gen_params=self.gen_params))
        self.m = m

        self.log_regs = self.gen_params.isa.reg_cnt
        self.phys_regs = 2**self.gen_params.phys_regs_bits

        self.to_execute_list = deque()
        self.expected_entries = [0 for _ in range(self.log_regs)]

        with self.run_simulation(m) as sim:
            for i in range(ports):
                sim.add_testbench(self.do_commit(i))
                sim.add_testbench(self.clear_chosen, background=True)
