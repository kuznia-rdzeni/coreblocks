from ..common import TestCaseWithSimulator, SimpleTestCircuit

from coreblocks.structs_common.rat import FRAT, RRAT
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config

from collections import deque
from random import Random


class TestFrontendRegisterAliasTable(TestCaseWithSimulator):
    def gen_input(self):
        while len(self.expected_entries) < self.log_regs:
            yield
        for _ in range(self.test_steps):
            rl = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rp = self.rand.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
            rl_s1 = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rl_s2 = self.rand.randrange(self.gen_params.isa.reg_cnt)

            self.to_execute_list.append({"rl": rl, "rp": rp, "rl_s1": rl_s1, "rl_s2": rl_s2})

    def do_rename(self):
        for _ in range(self.test_steps):
            while len(self.to_execute_list) == 0:
                yield
            to_execute = self.to_execute_list.pop()
            res = yield from self.m.rename.call(
                rl_dst=to_execute["rl"], rp_dst=to_execute["rp"], rl_s1=to_execute["rl_s1"], rl_s2=to_execute["rl_s2"]
            )
            self.assertEqual(res["rp_s1"], self.expected_entries[to_execute["rl_s1"]])
            self.assertEqual(res["rp_s2"], self.expected_entries[to_execute["rl_s2"]])

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

        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_rename)


class TestRetirementRegisterAliasTable(TestCaseWithSimulator):
    def gen_input(self):
        while len(self.expected_entries) < self.log_regs:
            yield
        for _ in range(self.test_steps):
            rl = self.rand.randrange(self.gen_params.isa.reg_cnt)
            rp = self.rand.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
            side_fx = self.rand.randrange(0, 2)

            self.to_execute_list.append({"rl": rl, "rp": rp, "side_fx": side_fx})

    def do_commit(self):
        for _ in range(self.test_steps):
            while len(self.to_execute_list) == 0:
                yield
            to_execute = self.to_execute_list.pop()
            res = yield from self.m.commit.call(
                rl_dst=to_execute["rl"], rp_dst=to_execute["rp"], side_fx=to_execute["side_fx"]
            )
            self.assertEqual(res["old_rp_dst"], self.expected_entries[to_execute["rl"]])

            if to_execute["side_fx"]:
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

        with self.run_simulation(m) as sim:
            sim.add_sync_process(self.gen_input)
            sim.add_sync_process(self.do_commit)
