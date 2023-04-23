from amaranth.utils import *
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters


class RegisterLayouts:
    def __init__(self, gen_params: GenParams, v_params: VectorParameters):
        self.read_resp = [("data", v_params.elen)]

        self.write = [
            ("addr", range(v_params.elems_in_bank)),
            ("data", v_params.elen),
            ("mask", v_params.bytes_in_elen),
        ]
        self.write_scalar = [("value", v_params.elen)]


class VRFFragmentLayouts:
    def __init__(self, gen_params: GenParams, v_params: VectorParameters):
        self.read_req = [("vrp_id", v_params.vrp_count_bits), ("elen_id", v_params.elems_in_bank_bits)]

        self.read_resp_i = [("vrp_id", v_params.vrp_count_bits)]
        self.read_resp_o = [("data", v_params.elen)]

        self.write = [
            ("vrp_id", v_params.vrp_count_bits),
            ("addr", log2_int(v_params.elems_in_bank)),
            ("data", v_params.elen),
            ("mask", v_params.bytes_in_elen),
        ]
