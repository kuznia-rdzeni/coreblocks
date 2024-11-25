from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.core_structs.rat import FRAT, RRAT
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from collections import deque
from random import Random

from transactron.testing.testbenchio import CallTrigger


class TestFrontendRegisterAliasTable(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            rl = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rp = self.rand.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
            rl_s1 = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rl_s2 = self.rand.randrange(self.gen_params.isa.reg_cnt)

            self.to_execute_list.append({"rl": rl, "rp": rp, "rl_s1": rl_s1, "rl_s2": rl_s2})

    async def do_rename(self, sim: TestbenchContext):
        for _ in range(self.test_steps):
            to_execute = self.to_execute_list.pop()
            res = await self.m.rename.call(
                sim,
                rl_dst=to_execute["rl"],
                rp_dst=to_execute["rp"],
                rl_s1=to_execute["rl_s1"],
                rl_s2=to_execute["rl_s2"],
            )
            assert res.rp_s1 == self.expected_entries[to_execute["rl_s1"]]
            assert res.rp_s2 == self.expected_entries[to_execute["rl_s2"]]

            self.expected_entries[to_execute["rl"]] = to_execute["rp"]

    def test_single(self):
        self.rand = Random(0)
        self.test_steps = 2000
        self.gen_params = GenParams(test_core_config.replace(phys_regs_bits=5, rob_entries_bits=6))
        m = SimpleTestCircuit(FRAT(gen_params=self.gen_params))
        self.m = m

        self.log_regs = self.gen_params.isa.reg_cnt
        self.phys_regs = 2**self.gen_params.phys_regs_bits

        self.to_execute_list = deque()
        self.expected_entries = [0 for _ in range(self.log_regs)]

        self.gen_input()
        with self.run_simulation(m) as sim:
            sim.add_testbench(self.do_rename)


class TestRetirementRegisterAliasTable(TestCaseWithSimulator):
    def gen_input(self):
        for _ in range(self.test_steps):
            rl = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rp = self.rand.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0

            self.to_execute_list.append({"rl": rl, "rp": rp})

    async def do_commit(self, sim: TestbenchContext):
        for _ in range(self.test_steps):
            to_execute = self.to_execute_list.pop()
            peek_res, res = (
                await CallTrigger(sim)
                .call(self.m.peek, rl_dst=to_execute["rl"])
                .call(self.m.commit, rl_dst=to_execute["rl"], rp_dst=to_execute["rp"])
            )
            assert peek_res is not None and res is not None
            assert res.old_rp_dst == self.expected_entries[to_execute["rl"]]
            assert peek_res.old_rp_dst == res["old_rp_dst"]

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
