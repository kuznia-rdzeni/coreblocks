import math
from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_status import *
from coreblocks.fu.vector_unit.v_translator import VectorTranslateLMUL
from collections import deque
import copy


class TestLMULTranslator(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 50
        self.gen_params = GenParams(test_core_config)
        self.v_params = VectorParameters(vlen = 1024, elen = 32)
        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.put = MethodMock(i=self.layouts.translator_in)
        self.report_mult = MethodMock(i=self.layouts.translator_report_multiplier_in)
        self.circ = SimpleTestCircuit(VectorTranslateLMUL(self.gen_params, self.v_params, self.put.get_method(), self.report_mult.get_method()))

        self.m = ModuleConnector(circ = self.circ, put=self.put, report= self.report_mult)

        self.received_instr=deque()
        self.received_multiplier = deque()

    @def_method_mock(lambda self: self.put, sched_prio = 1)
    def put_process(self, arg):
        self.received_instr.append(arg)

    @def_method_mock(lambda self: self.report_mult, sched_prio = 1)
    def report_mult_process(self, mult):
        self.received_multiplier.append(mult)

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
            instr = generate_instr(self.gen_params, self.layouts.translator_in, support_vector=True)
            yield from self.circ.issue.call(instr)
            expected_mult = math.ceil(lmul_to_float(instr["vtype"]["lmul"]))
            expected_list = self.generate_expected_list(instr)
            yield from self.tick(expected_mult)
            yield Settle()
            self.assertEqual(expected_mult, self.received_multiplier[0])
            self.assertIterableEqual(expected_list, self.received_instr)
            self.received_instr.clear()
            self.received_multiplier.clear()

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.put_process)
            sim.add_sync_process(self.report_mult_process)
