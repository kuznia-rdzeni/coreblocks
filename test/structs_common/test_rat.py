from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import VectorXRSLayout
from amaranth.utils import bits_for
from coreblocks.structs_common.rat import *
from collections import deque, defaultdict


def get_unique_generator():
    history = defaultdict(set)
    def f(cycle, generator):
        data = generator()
        while data in history[cycle]:
            data = generator()
        history[cycle].add(data)
        return data
    return f



class TestFRAT(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_cycles = 50
        self.superscalarity = 3
        self.gen_params = GenParams(test_core_config)

        self.virtual_rat = {}
        self.generated_dst = defaultdict(set)
        self.unique_rl_dst_generator = get_unique_generator()


    def create_process(self, k):
        def f():
            for _ in range(self.test_cycles):
                rl_s1 = generate_l_register_id(gen_params = self.gen_params)
                rl_s2 = generate_l_register_id(gen_params = self.gen_params)
                rp_dst = generate_phys_register_id(gen_params = self.gen_params)
                cycle = yield Now()
                rl_dst = self.unique_rl_dst_generator(cycle, lambda : generate_l_register_id(gen_params=self.gen_params))
                req = {"rl_s1" : rl_s1, "rl_s2" : rl_s2, "rl_dst":rl_dst, "rp_dst": rp_dst} 

                resp = yield from self.circ.rename_list[k].call(req)
                self.assertIsNotNone(resp)

                if rl_s1 in self.virtual_rat:
                    self.assertEqual(resp["rp_s1"], self.virtual_rat[rl_s1])
                if rl_s2 in self.virtual_rat:
                    self.assertEqual(resp["rp_s2"], self.virtual_rat[rl_s2])
                #defer to end of cycle
                yield Settle()
                self.virtual_rat[rl_dst]=rp_dst

                self.tick(random.randrange(2))
        return f

    def test_random(self):
        self.circ = SimpleTestCircuit(FRAT(gen_params=self.gen_params, superscalarity = self.superscalarity))
        with self.run_simulation(self.circ) as sim:
            for k in range(self.superscalarity):
                sim.add_sync_process(self.create_process(k))

class TestRRAT(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_cycles = 50
        self.superscalarity = 3
        self.gen_params = GenParams(test_core_config)

        self.virtual_rat = {}
        self.generated_dst = defaultdict(set)
