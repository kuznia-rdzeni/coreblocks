from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_status import *


def generate_vsetvl(
    gen_params: GenParams,
    layout: LayoutLike,
    last_vl: int = 0,
    const_lmul: Optional[LMUL] = None,
    allow_illegal: bool = False,
    max_vl : Optional[int] = None,
    max_reg_bits : Optional[int] = None,
):
    v_params = gen_params.v_params
    instr = generate_instr(gen_params, layout, max_vl = max_vl, max_reg_bits = max_reg_bits)
    vtype = generate_vtype(gen_params, max_vl = max_vl)
    if const_lmul is not None:
        vtype["lmul"] = const_lmul
    imm2 = convert_vtype_to_imm(vtype)
    while not allow_illegal and eew_to_bits(vtype["sew"]) > v_params.elen:
        vtype = generate_vtype(gen_params, max_vl = max_vl)
        if const_lmul is not None:
            vtype["lmul"] = const_lmul
        imm2 = convert_vtype_to_imm(vtype)
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


def get_vector_instr_generator():
    last_vtype = {"vl": 0, "ma": 0, "ta": 0, "sew": 0, "lmul": 0}
    first_instr = True
    next_rob_id = 0
    last_vl = 0


    def f(
        gen_params: GenParams,
        layout: LayoutLike,
        not_balanced_vsetvl=False,
        vsetvl_different_rp_id: bool = False, # useful when doing updates in RS which should be tracked
        const_lmul: Optional[LMUL] = None,
        max_vl : Optional[int] = None,
        random_rob_id = True,
        **kwargs
    ):
        def edit_rob_id(instr):
            if not random_rob_id:
                nonlocal next_rob_id
                instr["rob_id"] = next_rob_id 
                next_rob_id +=1
                next_rob_id %= 2**gen_params.rob_entries_bits
            return instr

        nonlocal last_vtype
        nonlocal first_instr
        nonlocal last_vl
        if first_instr:
            instr, last_vtype = generate_vsetvl(gen_params, layout, const_lmul=const_lmul, max_vl = max_vl, max_reg_bits = kwargs.get("max_reg_bits", None))
            first_instr = False
            instr = edit_rob_id(instr)
            return instr, last_vtype

        instr = generate_instr(gen_params, layout, max_vl = max_vl, **kwargs)
        if instr["exec_fn"]["op_type"] == OpType.V_CONTROL or (not_balanced_vsetvl and random.randrange(2)):
            while True:
                instr, last_vtype = generate_vsetvl(gen_params, layout, const_lmul=const_lmul, max_vl = max_vl, last_vl = last_vl, max_reg_bits = kwargs.get("max_reg_bits", None))
                if not( vsetvl_different_rp_id and instr["rp_s1"]["id"] == instr["rp_s2"]["id"]):
                    break
            last_vl = last_vtype["vl"]

        instr = edit_rob_id(instr)
        return instr, last_vtype

    return f

def expand_mask(mask):
    m = 0
    for b in bin(mask)[2:]:
        m <<= 8
        if b == "1":
            m |= 0xFF
    return m

def elem_mask_to_byte_mask(elen, mask, eew):
    m = 0
    bits = eew_to_bits(eew)
    mask = ("{:0" + str(elen//bits) + "b}").format(mask)
    while elen !=0:
        elen -= bits
        m <<= (bits // 8)
        if mask[0] == "1":
            m |= 2**(bits // 8) - 1
        mask = mask[1:]
    return m

def execute_flexible_operation(op: Callable, in1: int, in2: int, elen: int, eew: EEW) -> int:
    def split_flex(n: int, elen: int, eew: EEW):
        ebits = eew_to_bits(eew)
        while elen > 0:
            yield n % (2**ebits)
            n = n >> ebits
            elen -= ebits


    def glue_flex(elems: list[int], elen: int, eew: EEW) -> int:
        out = 0
        ebits = eew_to_bits(eew)
        mask = 2**ebits - 1
        for elem in reversed(elems):
            out = (out << ebits) | (elem & mask)
        return out

    out_elems = []
    for elem1, elem2 in zip(split_flex(in1, elen, eew), split_flex(in2, elen, eew)):
        out_elems.append(op(elem1, elem2))
    return glue_flex(out_elems, elen, eew)


def get_funct6_to_op(eew):
    eew_bits = eew_to_bits(eew)
    return {
    Funct6.VADD : lambda x, y: x+y,
    Funct6.VSUB : lambda x, y: x-y,
    Funct6.VSRA : lambda x, y: signed_to_int(x, eew_bits)>> (y % 2**log2_int(eew_bits)),
    Funct6.VSLL : lambda x, y: x<< (y% 2**log2_int(eew_bits)),
    Funct6.VSRL : lambda x, y: x >> (y % 2**log2_int(eew_bits)),
    Funct6.VMSLE : lambda x, y: int(signed_to_int(x, eew_bits)<=signed_to_int(y, eew_bits)),
    Funct6.VMSLEU : lambda x, y: int(x<=y),
    Funct6.VMSLT : lambda x, y: int(signed_to_int(x, eew_bits)<signed_to_int(y, eew_bits)),
    Funct6.VMSLTU : lambda x, y: int(x<y),
    Funct6.VMSEQ : lambda x, y: int(x==y),
    Funct6.VXOR : lambda x, y: x^y,
    Funct6.VOR : lambda x, y: x|y,
    Funct6.VAND : lambda x, y: x&y,
    Funct6.VMIN : lambda x, y: min(signed_to_int(x, eew_bits),signed_to_int(y, eew_bits)),
    Funct6.VMINU : lambda x, y: min(x,y),
    Funct6.VMAX : lambda x, y: max(signed_to_int(x, eew_bits),signed_to_int(y, eew_bits)),
    Funct6.VMAXU : lambda x, y: max(x, y),
    }


def generate_funct7_from_funct6(funct6 : Iterable[Funct6 | int]) -> list[int]:
    output = []
    for x in funct6:
        output += [x*2, x*2 + 1]
    return output
