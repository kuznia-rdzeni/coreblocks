from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_status import *
from collections import deque


def generate_vsetvl(gen_params: GenParams, v_params: VectorParameters, layout: LayoutLike, last_vl: int = 0):
    instr = generate_instr(gen_params, layout)
    vtype = generate_vtype(gen_params)
    imm2 = convert_vtype_to_imm(vtype)
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


def generate_vector_instr(gen_params: GenParams, v_params: VectorParameters, layout: LayoutLike, not_balanced_vsetvl = False):
    instr = generate_instr(gen_params, layout, support_vector = True)
    if instr["exec_fn"]["op_type"]==OpType.V_CONTROL or (not_balanced_vsetvl and random.randrange(2)):
        instr = get_dict_subset(generate_vsetvl(gen_params, v_params, layout)[0], [field[0] for field in layout])
    return instr
