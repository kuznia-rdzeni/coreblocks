from amaranth import *
from test.common import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_executor import *
from test.fu.vector_unit.common import *


class TestVectorExecutor(TestCaseWithSimulator):
    """
    This tests has two main goals:
    - check for liveness of VectorExecutor (if every input will end)
    - check if creation of VectorExecutor works

    Checking results of execution can be added whith LSU support.
    """

    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(
            test_vector_core_config.replace(vector_config=VectorUnitConfiguration(vrp_count=8, _vrl_count=7))
        )
        self.test_number = 40
        self.fragment_index = 1
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)

        self.end_reporter = MethodMock()
        self.circ = SimpleTestCircuit(
            VectorExecutor(self.gen_params, self.fragment_index, self.end_reporter.get_method())
        )
        self.m = ModuleConnector(circ=self.circ, end_reporter=self.end_reporter)

        self.end_counter = 0

    @def_method_mock(lambda self: self.end_reporter, sched_prio=1)
    def end_reporter_process(self):
        self.end_counter += 1

    def generate_input(self):
        instr = generate_instr(
            self.gen_params,
            self.layout.executor_in,
            support_vector=True,
            optypes=[OpType.V_ARITHMETIC],
            funct7=generate_funct7_from_funct6(get_funct6_to_op(EEW.w8).keys()),
            max_vl=self.v_params.vlen // 8,
            funct3=[Funct3.OPIVI, Funct3.OPIVV, Funct3.OPIVX],
            overwriting={
                "rp_s2": {"type": RegisterType.V},
                "rp_dst": {"type": RegisterType.V},
                "rp_s3": {"type": RegisterType.V},
            },
        )
        return instr

    def process(self):
        for _ in range(self.test_number):
            input = self.generate_input()
            yield from self.circ.issue.call(input)
        while self.end_counter < self.test_number:
            yield

    def test_random(self):
        with self.run_simulation(self.m, 5000) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.end_reporter_process)
