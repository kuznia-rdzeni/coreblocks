from amaranth import *
from test.common import *
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
        self.scoreboard_layout = ScoreboardLayouts(self.v_params.vrp_count)
        self.v_retirement_layout = VectorRetirementLayouts(self.gen_params)

        self.put = MethodMock(i=self.gen_params.get(FuncUnitLayouts).accept)
        self.update_vvrs = MethodMock(i=self.vvrs_layouts.update_in)
        self.scoreboard_set = MethodMock(i=self.scoreboard_layout.set_dirty_in)
        self.report_end = MethodMock(i=self.v_retirement_layout.report_end)
        self.circ = SimpleTestCircuit(
            VectorExecutionEnder(
                self.gen_params,
                self.put.get_method(),
                self.update_vvrs.get_method(),
                self.scoreboard_set.get_method(),
                self.report_end.get_method(),
            )
        )
        self.m = ModuleConnector(
            circ=self.circ,
            put=self.put,
            update_vvrs=self.update_vvrs,
            scoreboard_set=self.scoreboard_set,
            report_end=self.report_end,
        )

        self.received_data = None
        self.received_vvrs_update = None
        self.received_scoreboard_set = None
        self.received_report_end = None
        self.send_data = deque()
        self.enders_barrier = SimBarrier(self.v_params.register_bank_count)

    @def_method_mock(lambda self: self.put, sched_prio=1)
    def put_process(self, arg):
        self.assertIsNone(self.received_data)
        self.received_data = arg

    @def_method_mock(lambda self: self.update_vvrs, sched_prio=1)
    def update_vvrs_process(self, arg):
        self.assertIsNone(self.received_vvrs_update)
        self.received_vvrs_update = arg

    @def_method_mock(lambda self: self.scoreboard_set, sched_prio=1)
    def scoreboard_set_process(self, arg):
        self.assertIsNone(self.received_scoreboard_set)
        self.received_scoreboard_set = arg

    @def_method_mock(lambda self: self.report_end, sched_prio=1)
    def report_end_process(self, arg):
        self.received_report_end = arg

    def init_process(self):
        for _ in range(self.test_number):
            input = generate_instr(self.gen_params, self.layout.ender_init_in, support_vector=True, max_reg_bits=5)
            yield from self.circ.init.call(input)
            self.send_data.append(input)

    def end_process_generator(self, k):
        def f():
            for _ in range(self.test_number):
                yield from self.circ.end_list[k].call()
                yield from self.enders_barrier.wait()

                if k == 0:  # check only using one process
                    self.assertIsNotNone(self.received_data)
                    assert self.received_data is not None
                    expected = self.send_data.popleft()
                    self.assertEqual(self.received_data["exception"], 0)
                    self.assertEqual(self.received_data["result"], 0)
                    self.assertEqual(self.received_data["rob_id"], expected["rob_id"])
                    self.assertEqual(self.received_data["rp_dst"], expected["rp_dst"])

                    if expected["rp_dst"]["type"] == RegisterType.V:
                        assert self.received_vvrs_update is not None
                        assert self.received_scoreboard_set is not None
                        assert self.received_report_end is not None
                        self.assertEqual(self.received_scoreboard_set["id"], expected["rp_dst"]["id"])
                        self.assertEqual(self.received_scoreboard_set["dirty"], 0)

                        self.assertEqual(self.received_vvrs_update["tag"], expected["rp_dst"])

                        self.assertEqual(self.received_report_end["rob_id"], expected["rob_id"])
                        self.assertEqual(self.received_report_end["rp_dst"], expected["rp_dst"])
                    else:
                        self.assertIsNone(self.received_vvrs_update)
                        self.assertIsNone(self.received_scoreboard_set)
                        self.assertIsNone(self.received_report_end)

                    self.received_data = None
                    self.received_vvrs_update = None
                    self.received_scoreboard_set = None
                    self.received_report_end = None

        return f

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.init_process)
            sim.add_sync_process(self.put_process)
            sim.add_sync_process(self.update_vvrs_process)
            sim.add_sync_process(self.scoreboard_set_process)
            sim.add_sync_process(self.report_end_process)
            for k in range(self.v_params.register_bank_count):
                sim.add_sync_process(self.end_process_generator(k))
