from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_execution_ender import *
from test.fu.vector_unit.common import *
from collections import deque

class TestVectorExecutionEnder(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 50
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)
        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.v_params.vvrs_entries_bits)
        self.scoreboard_layout = ScoreboardLayouts(self.gen_params.v_params.vrp_count)

        self.put = MethodMock(i = self.gen_params.get(FuncUnitLayouts).accept)
        self.update_vvrs = MethodMock(i = self.vvrs_layouts.update_in)
        self.scoreboard_set = MethodMock(i = self.scoreboard_layout.set_dirty_in)
        self.circ = SimpleTestCircuit(VectorExecutionEnder(self.gen_params, self.put.get_method(), self.update_vvrs.get_method(), self.scoreboard_set.get_method()))
        self.m = ModuleConnector(circ=self.circ, put=self.put, update_vvrs = self.update_vvrs, scoreboard_set= self.scoreboard_set)
        
        self.received_data = None
        self.send_data = deque()

    @def_method_mock(lambda self: self.put, sched_prio = 2)
    def put_process(self, arg):
        self.assertIsNone(self.received_data)
        self.received_data = arg

    @def_method_mock(lambda self: self.update_vvrs, sched_prio = 2)
    def update_vvrs_process(self, arg):
        pass

    @def_method_mock(lambda self: self.scoreboard_set, sched_prio = 2)
    def scoreboard_set_process(self, arg):
        pass

    def init_process(self):
        for _ in range(self.test_number):
            input = generate_instr(self.gen_params, self.layout.ender_init_in, support_vector = True)
            yield from self.circ.init.call(input)
            self.send_data.append(input)

    def end_process_generator(self, k):
        def f():
            for _ in range(self.test_number):
                yield from self.circ.end.call()
                self.assertIsNotNone(self.received_data)
                
                assert self.received_data is not None
                expected = self.send_data.popleft()
                self.assertEqual(self.received_data["exception"], 0)
                self.assertEqual(self.received_data["result"], 0)
                self.assertEqual(self.received_data["rob_id"], expected["rob_id"])
                self.assertEqual(self.received_data["rp_dst"], expected["rp_dst"])

                self.received_data = None
        return f

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.init_process)
            sim.add_sync_process(self.put_process)
            sim.add_sync_process(self.update_vvrs_process)
            sim.add_sync_process(self.scoreboard_set_process)
            for k in range(self.v_params.register_bank_count):
                sim.add_sync_process(self.end_process_generator(k))
