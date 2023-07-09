from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_alloc_rename import *
from coreblocks.transactions.lib import *
from coreblocks.structs_common.rat import FRAT
from coreblocks.structs_common.superscalar_freerf import SuperscalarFreeRF
from test.fu.vector_unit.common import *


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
        self.circ = SimpleTestCircuit(
            VectorAllocRename(
                self.gen_params,
                self.freerf.allocate,
                self.frat.get_rename_list[0],
                self.frat.get_rename_list[1],
                self.frat.set_rename_list[0],
            )
        )
        self.m = ModuleConnector(circ=self.circ, frat=self.frat, freerf=self.freerf, dealocate=self.deallocate)

        self.generate_vector_instr = get_vector_instr_generator()

    def process(self):
        for _ in range(self.test_number):
            instr, _ = self.generate_vector_instr(self.gen_params, self.layout.alloc_rename_in)
            out = yield from self.circ.issue.call(instr)
            for field_name in ["rob_id", "exec_fn", "vtype"]:
                self.assertEqual(instr[field_name], out[field_name])
            yield from self.deallocate.call(reg=out["rp_dst"]["id"])

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
