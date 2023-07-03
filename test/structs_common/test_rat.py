from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import VectorXRSLayout
from amaranth.utils import bits_for
from coreblocks.structs_common.rat import *
from collections import deque, defaultdict


class TestFRAT(TestCaseWithSimulator):
    def setUp(self):
        random.seed(15)
        self.test_cycles = 4000
        self.superscalarity = 5
        self.gen_params = GenParams(test_core_config)

        self.circ = SimpleTestCircuit(FRAT(gen_params=self.gen_params, superscalarity = self.superscalarity))
        self.virtual_rat = {}
        self.generated_dst = defaultdict(set)

    def generate_dst(self, cycle):
        rl_dst = random.randrange(self.gen_params.isa.reg_cnt)
        rp_dst = random.randrange(2**self.gen_params.phys_regs_bits)
        while rl_dst in self.generated_dst[cycle]:
            rl_dst += 1
            rl_dst %= self.gen_params.isa.reg_cnt
        self.generated_dst[cycle].add(rl_dst)
        return rl_dst, rp_dst

    def create_process(self, k):
        def f():
            for cycle in range(self.test_cycles):
                rl_s1 = random.randrange(self.gen_params.isa.reg_cnt)
                rl_s2 = random.randrange(self.gen_params.isa.reg_cnt)
                rl_dst, rp_dst = self.generate_dst(cycle)
                req = {"rl_s1" : rl_s1, "rl_s2" : rl_s2, "rl_dst":rl_dst, "rp_dst": rp_dst} 

                resp = yield from self.circ.rename_list[k].call_try(req)
                self.assertIsNotNone(resp)

                if rl_s1 in self.virtual_rat:
                    self.assertEqual(resp["rp_s1"], self.virtual_rat[rl_s1])
                if rl_s2 in self.virtual_rat:
                    self.assertEqual(resp["rp_s2"], self.virtual_rat[rl_s2])
                #defer to end of cycle
                yield Settle()
                self.virtual_rat[rl_dst]=rp_dst
        return f

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            for k in range(self.superscalarity):
                sim.add_sync_process(self.create_process(k))
