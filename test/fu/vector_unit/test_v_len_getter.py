from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_len_getter import *
from coreblocks.transactions.lib import *
from coreblocks.structs_common.rat import FRAT
from coreblocks.structs_common.superscalar_freerf import SuperscalarFreeRF
from test.fu.vector_unit.common import *
from parameterized import parameterized_class


test_bank_count = 4


@parameterized_class(["fragment_index", "seed"], [(i, i) for i in range(test_bank_count)])
class TestVectorLenGetter(TestCaseWithSimulator):
    fragment_index: int
    seed: int

    def setUp(self):
        random.seed(self.seed)
        self.gen_params = GenParams(
            test_vector_core_config.replace(vector_config=VectorUnitConfiguration(register_bank_count=test_bank_count))
        )
        self.test_number = 50
        self.max_vl = 128
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)

        self.circ = SimpleTestCircuit(VectorLenGetter(self.gen_params, self.fragment_index))

        self.generate_vector_instr = get_vector_instr_generator()

    def process(self):
        for _ in range(self.test_number):
            instr, _ = self.generate_vector_instr(self.gen_params, self.layout.executor_in, max_vl=self.max_vl)
            result = yield from self.circ.issue.call(instr)
            elems_in_bank = self.gen_params.v_params.eew_to_elems_in_bank[instr["vtype"]["sew"]]
            end_fragment = (instr["vtype"]["vl"] - 1) // elems_in_bank

            elems_in_fragment = instr["vtype"]["vl"] % elems_in_bank
            elems_in_elen = self.v_params.elen // eew_to_bits(instr["vtype"]["sew"])

            if end_fragment == self.fragment_index:
                if elems_in_fragment == 0:
                    expected_len = self.v_params.elens_in_bank
                else:
                    expected_len = elems_in_fragment // elems_in_elen
                expected_last_mask = int("0" + "1" * (elems_in_fragment % elems_in_elen), 2)
                if elems_in_fragment % elems_in_elen != 0:
                    expected_len += 1
                else:
                    expected_last_mask = 2**elems_in_elen - 1
            elif end_fragment < self.fragment_index:
                expected_len = 0
                expected_last_mask = 0
            else:
                expected_len = self.v_params.elens_in_bank
                expected_last_mask = 2**elems_in_elen - 1

            self.assertEqual(result["elens_len"], expected_len)
            self.assertEqual(result["last_mask"], expected_last_mask)

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.process)
