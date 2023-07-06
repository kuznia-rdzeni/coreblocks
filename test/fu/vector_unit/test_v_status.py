from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_status import *
from collections import deque

def generate_vsetvl_imm(gen_params) -> tuple[int, dict]:
    vtype = generate_vtype(gen_params)
    imm = convert_vtype_to_imm(vtype)
    return imm, get_dict_without(vtype, ["vl"])


def generate_vsetvl(gen_params: GenParams, v_params: VectorParameters, layout: LayoutLike, last_vl: int):
    instr = generate_instr(gen_params, layout)
    imm2, vtype = generate_vsetvl_imm(gen_params)
    if eew_to_bits(vtype["sew"]) > v_params.elen:
        imm2 = 0
        vtype = {"sew": EEW(0), "lmul": LMUL(0), "ta": 0, "ma": 0}
    vsetvl_type = random.randrange(4)
    if vsetvl_type == 2:
        instr = overwrite_dict_values(instr, {"s2_val": imm2})
    if vsetvl_type == 3:
        instr = overwrite_dict_values(instr, {"imm": instr["rp_s1"]["id"]})
    imm2 |= vsetvl_type << 10
    instr = overwrite_dict_values(
        instr, {"imm2": imm2, "exec_fn": {"op_type": OpType.V_CONTROL, "funct3": Funct3.OPCFG}}
    )

    vlmax = int(v_params.vlen // eew_to_bits(vtype["sew"]) * lmul_to_float(vtype["lmul"]))

    if vsetvl_type == 3:
        vtype |= {"vl": instr["rp_s1"]["id"]}
    else:
        if instr["rp_s1"]["id"] == 0:
            vtype |= {"vl": vlmax}
        else:
            vtype |= {"vl": instr["s1_val"]}

    if instr["rp_s1"]["id"] == 0 and instr["rp_dst"]["id"] == 0:
        vtype |= {"vl": last_vl}

    return instr, vtype


class TestVectorStatusUnit(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_core_config)
        self.test_number = 700
        self.v_params = VectorParameters(vlen=1024, elen=32)

        self.vf_layout = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.put_instr = TestbenchIO(Adapter(i=self.vf_layout.status_out))
        self.retire = TestbenchIO(Adapter(i=FuncUnitLayouts(self.gen_params).accept))

        self.circ = SimpleTestCircuit(
            VectorStatusUnit(self.gen_params, self.v_params, self.put_instr.adapter.iface, self.retire.adapter.iface)
        )

        self.m = ModuleConnector(circ=self.circ, put_instr=self.put_instr, retire=self.retire)

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
            instr, vtype = generate_vsetvl(self.gen_params, self.v_params, self.vf_layout.status_in, 0)
            data_vsetvl_q.append((instr, vtype))
            yield from self.circ.issue.call(instr)
            current_vtype = vtype
            for _ in range(self.test_number):
                if random.randrange(2):
                    while data := generate_instr(self.gen_params, self.vf_layout.verification_in, support_vector=True):
                        if data["exec_fn"]["op_type"] != OpType.V_CONTROL:
                            break
                    data_normal_q.append((data, current_vtype))
                else:
                    data, current_vtype = generate_vsetvl(
                        self.gen_params, self.v_params, self.vf_layout.verification_in, current_vtype["vl"]
                    )
                    data_vsetvl_q.append((data, current_vtype))
                yield from self.circ.issue.call(data)
            # wait few cycles to be sure that all mocks were called
            for _ in range(2):
                yield

            self.assertEqual(len(data_normal_q), len(put_q))
            self.assertEqual(len(data_vsetvl_q), len(retire_q))

            for (org_data, org_vtype), resp in zip(data_normal_q, put_q):
                self.assertDictContainsSubset(get_dict_without(org_data, ["imm2"]), resp)
                self.assertDictContainsSubset({"vtype": org_vtype}, resp)

            for (org_data, org_vtype), retire_data in zip(data_vsetvl_q, retire_q):
                self.assertEqual(retire_data["exception"], 0)
                for field in ["rp_dst", "rob_id"]:
                    self.assertEqual(org_data[field], retire_data[field])
                if org_data["rp_dst"]["id"] != 0:
                    self.assertEqual(org_vtype["vl"], retire_data["result"])

        with self.run_simulation(self.m) as sim:
            for mock in create_mocks():
                sim.add_sync_process(mock)
            sim.add_sync_process(process)
