from amaranth import *
from test.common import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_alloc_rename import *
from coreblocks.structs_common.rat import FRAT
from coreblocks.structs_common.superscalar_freerf import SuperscalarFreeRF
from test.fu.vector_unit.common import *
from collections import deque


class TestVectorAllocRename(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 100
        self.v_params = self.gen_params.v_params

        self.layout = VectorFrontendLayouts(self.gen_params)

        self.frat = FRAT(gen_params=self.gen_params, superscalarity=2)
        self.freerf = SuperscalarFreeRF(self.v_params.vrp_count, 1)
        self.deallocate = TestbenchIO(AdapterTrans(self.freerf.deallocates[0]))
        self.initialise_list = [MethodMock() for _ in range(self.v_params.vrp_count)]
        self.initialise_process_list = []
        self.circ = SimpleTestCircuit(
            VectorAllocRename(
                self.gen_params,
                self.freerf.allocate,
                self.frat.get_rename_list[0],
                self.frat.get_rename_list[1],
                self.frat.set_rename_list[0],
                [mock.get_method() for mock in self.initialise_list],
            )
        )
        self.m = ModuleConnector(
            circ=self.circ,
            frat=self.frat,
            freerf=self.freerf,
            dealocate=self.deallocate,
            initialise=ModuleConnector(*self.initialise_list),
        )

        self.generate_vector_instr = get_vector_instr_generator()
        self.initialise_requests = deque()

        for i in range(self.v_params.vrp_count):

            def create_mock(i):
                @def_method_mock(lambda: self.initialise_list[i], sched_prio=1)
                def f():
                    self.initialise_requests.append(i)

                return f

            self.initialise_process_list.append(create_mock(i))

    def process(self):
        for _ in range(self.test_number):
            instr, _ = self.generate_vector_instr(self.gen_params, self.layout.alloc_rename_in)
            out = yield from self.circ.issue.call(instr)
            for field_name in ["rob_id", "exec_fn", "vtype"]:
                self.assertEqual(instr[field_name], out[field_name])
            yield Settle()
            if instr["rp_dst"]["type"] == RegisterType.V:
                initialised_reg = self.initialise_requests.popleft()
                self.assertEqual(initialised_reg, out["rp_dst"]["id"])
            yield from self.deallocate.call(reg=out["rp_dst"]["id"])

    def test_random(self):
        assert self.initialise_process_list[0] is not self.initialise_process_list[1]
        with self.run_simulation(
            self.m,
        ) as sim:
            sim.add_sync_process(self.process)
            for f in self.initialise_process_list:
                sim.add_sync_process(f)
