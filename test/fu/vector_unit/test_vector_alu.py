from amaranth import *
from test.common import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vector_alu import *
from test.fu.vector_unit.common import *


class TestVectorBasicFlexibleAlu(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 20
        self.v_params = self.gen_params.v_params

        self.layout = VectorAluLayouts(self.gen_params)

        self.put = MethodMock(i=self.layout.alu_out)
        self.circ = SimpleTestCircuit(VectorBasicFlexibleAlu(self.gen_params, self.put.get_method()))
        self.m = ModuleConnector(circ=self.circ, put=self.put)

        self.received_data = None

    @def_method_mock(lambda self: self.put, sched_prio=1)
    def put_process(self, dst_val):
        self.received_data = dst_val

    def generate_input(self, funct6):
        while True:
            eew = random.choice(list(EEW))
            if eew_to_bits(eew) <= self.v_params.elen:
                break
        return {
            "s1": random.randrange(2**self.v_params.elen),
            "s2": random.randrange(2**self.v_params.elen),
            "eew": eew,
            "exec_fn": generate_exec_fn([OpType.V_ARITHMETIC], [funct6 * 2, funct6 * 2 + 1]),
        }

    def process(self):
        for funct6 in get_funct6_to_op(EEW.w8).keys():
            for _ in range(self.test_number):
                input = self.generate_input(funct6)
                yield from self.circ.issue.call(input)
                yield Settle()
                self.assertIsNotNone(self.received_data)
                expected_out = execute_flexible_operation(
                    get_funct6_to_op(input["eew"])[funct6], input["s1"], input["s2"], self.v_params.elen, input["eew"]
                )
                self.assertEqual(expected_out, self.received_data)
                self.received_data = None

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.put_process)
