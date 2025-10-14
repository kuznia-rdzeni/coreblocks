from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rat import RRAT
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from collections import deque
from random import Random


class TestRetirementRegisterAliasTable(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            rl = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rp = self.rand.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0

            self.to_execute_list.append({"rl": rl, "rp": rp})

    async def do_commit(self, sim: TestbenchContext):
        # wait until R-RAT clears itself after reset
        await self.tick(sim, self.gen_params.isa.reg_cnt)
        for _ in range(self.test_steps):
            to_execute = self.to_execute_list.pop()
            if self.rand.randrange(2):
                peek_res = await self.m.peek.call(sim, rl_dst=to_execute["rl"])
                assert peek_res.old_rp_dst == self.expected_entries[to_execute["rl"]]
            res = await self.m.commit.call(sim, rl_dst=to_execute["rl"], rp_dst=to_execute["rp"])
            assert res.old_rp_dst == self.expected_entries[to_execute["rl"]]

            self.expected_entries[to_execute["rl"]] = to_execute["rp"]

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 2000
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=5, rob_entries_bits=6))
        m = SimpleTestCircuit(RRAT(gen_params=self.gen_params))
        self.m = m

        self.log_regs = self.gen_params.isa.reg_cnt
        self.phys_regs = 2**self.gen_params.phys_regs_bits

        self.to_execute_list = deque()
        self.expected_entries = [0 for _ in range(self.log_regs)]

        self.gen_input()
        with self.run_simulation(m) as sim:
            sim.add_testbench(self.do_commit)
