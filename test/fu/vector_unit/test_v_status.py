from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_status import *
from test.fu.vector_unit.common import *
from collections import deque


class TestVectorStatusUnit(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 300

        self.vf_layout = VectorFrontendLayouts(self.gen_params)
        self.put_instr = MethodMock(i=self.vf_layout.status_out)
        self.retire = MethodMock(i=FuncUnitLayouts(self.gen_params).accept)

        self.circ = SimpleTestCircuit(
            VectorStatusUnit(self.gen_params, self.put_instr.get_method(), self.retire.get_method())
        )

        self.m = ModuleConnector(circ=self.circ, put_instr=self.put_instr, retire=self.retire)

        self.vector_instr_generator = get_vector_instr_generator()

    def test_passing(self):
        data_normal_q = deque()
        data_vsetvl_q = deque()
        put_q = deque()
        retire_q = deque()

        def create_mocks():
            @def_method_mock(lambda: self.put_instr)
            def put_instr(arg):
                put_q.append(arg)

            @def_method_mock(lambda: self.retire)
            def retire(arg):
                retire_q.append(arg)

            return put_instr, retire

        def process():
            self.assertEqual((yield from self.circ.get_vill.call())["vill"], 1)
            for _ in range(self.test_number):
                instr, vtype = self.vector_instr_generator(self.gen_params, self.vf_layout.verification_in, not_balanced_vsetvl = True, max_reg_bits = 5)
                if instr["exec_fn"]["op_type"] != OpType.V_CONTROL:
                    data_normal_q.append((instr, vtype))
                else:
                    data_vsetvl_q.append((instr, vtype))
                yield from self.circ.issue.call(instr)
            # wait few cycles to be sure that all mocks were called
            for _ in range(2):
                yield

            self.assertEqual(len(data_normal_q), len(put_q))
            self.assertEqual(len(data_vsetvl_q), len(retire_q))

            for (org_data, org_vtype), retire_data in zip(data_vsetvl_q, retire_q):
                self.assertEqual(retire_data["exception"], 0)
                for field in ["rp_dst", "rob_id"]:
                    self.assertEqual(org_data[field], retire_data[field])
                if org_data["rp_dst"]["id"] != 0:
                    self.assertEqual(org_vtype["vl"], retire_data["result"])

            for (org_data, org_vtype), resp in zip(data_normal_q, put_q):
                self.assertDictContainsSubset(get_dict_without(org_data, ["imm2"]), resp)
                self.assertDictContainsSubset({"vtype": org_vtype}, resp)

        with self.run_simulation(self.m) as sim:
            for mock in create_mocks():
                sim.add_sync_process(mock)
            sim.add_sync_process(process)
