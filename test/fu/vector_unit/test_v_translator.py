import math
from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_status import *
from coreblocks.fu.vector_unit.v_translator import VectorTranslateLMUL, VectorTranslateRS3
from collections import deque
import copy


class TestLMULTranslator(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 50
        self.gen_params = GenParams(test_core_config)
        self.v_params = VectorParameters(vlen = 1024, elen = 32)
        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.put = MethodMock(i=self.layouts.translator_inner)
        self.circ = SimpleTestCircuit(VectorTranslateLMUL(self.gen_params, self.v_params, self.put.get_method()))

        self.m = ModuleConnector(circ = self.circ, put=self.put)

        self.received_instr=deque()

    @def_method_mock(lambda self: self.put, sched_prio = 1)
    def put_process(self, arg):
        self.received_instr.append(arg)

    def generate_expected_list(self, instr):
        lmul = math.ceil(lmul_to_float(instr["vtype"]["lmul"]))
        instr["rp_s1"]["id"] -= (instr["rp_s1"]["id"]%lmul)
        instr["rp_s2"]["id"] -= (instr["rp_s2"]["id"]%lmul)
        instr["rp_dst"]["id"] -= (instr["rp_dst"]["id"]%lmul)
        instr["vtype"]["lmul"]=LMUL.m1 if lmul > 1 else instr["vtype"]["lmul"]
        out = []
        for i in range(lmul):
            instr_new = copy.deepcopy(instr)
            instr_new["rp_s1"]["id"] +=i
            instr_new["rp_s2"]["id"] +=i
            instr_new["rp_dst"]["id"] +=i
            out.append(instr_new)
        return out


    def process(self):
        for _ in range(self.test_number):
            instr = generate_instr(self.gen_params, self.layouts.translator_inner, support_vector=True)
            received_mult = (yield from self.circ.issue.call(instr))["mult"]
            expected_mult = math.ceil(lmul_to_float(instr["vtype"]["lmul"]))
            expected_list = self.generate_expected_list(instr)
            yield from self.tick(expected_mult)
            yield Settle()
            self.assertEqual(expected_mult, received_mult)
            self.assertIterableEqual(expected_list, self.received_instr)
            self.received_instr.clear()

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.put_process)

class TestVectorTranslateRS3(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 50
        self.gen_params = GenParams(test_core_config)
        self.v_params = VectorParameters(vlen = 1024, elen = 32)
        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.put = MethodMock(i=self.layouts.translator_out)
        self.circ = SimpleTestCircuit(VectorTranslateRS3(self.gen_params, self.v_params, self.put.get_method()))

        self.m = ModuleConnector(circ = self.circ, put=self.put)

        self.received_instr=deque()

    @def_method_mock(lambda self: self.put, sched_prio = 1)
    def put_process(self, arg):
        self.received_instr.append(arg)

    def generate_expected_instr(self, instr):
        return instr | {"rp_s3" : instr["rp_dst"], "rp_v0" : {"id" : 0}}

    def process(self):
        for _ in range(self.test_number):
            instr = generate_instr(self.gen_params, self.layouts.translator_inner, support_vector=True)
            yield from self.circ.issue.call(instr)
            expected_instr = self.generate_expected_instr(instr)
            yield Settle()
            self.assertEqual(expected_instr, self.received_instr[0])
            self.received_instr.clear()

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.put_process)
