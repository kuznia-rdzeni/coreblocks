from amaranth.utils import *
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.utils import EEW
from coreblocks.utils._typing import LayoutLike
from coreblocks.utils import layout_subset


class VectorRegisterBankLayouts:
    def __init__(self, gen_params: GenParams, v_params: VectorParameters):
        self.read_resp = [("data", v_params.elen)]

        self.write = [
            ("addr", range(v_params.elems_in_bank)),
            ("data", v_params.elen),
            ("mask", v_params.bytes_in_elen),
        ]
        self.write_scalar = [("value", v_params.elen)]

        self.initialize = [("eew", EEW)]


class VRFFragmentLayouts:
    def __init__(self, gen_params: GenParams, v_params: VectorParameters):
        self.read_req = [("vrp_id", v_params.vrp_count_bits), ("addr", v_params.elems_in_bank_bits)]

        self.read_resp_i = [("vrp_id", v_params.vrp_count_bits)]
        self.read_resp_o = [("data", v_params.elen)]

        self.write = [
            ("vrp_id", v_params.vrp_count_bits),
            ("addr", log2_int(v_params.elems_in_bank)),
            ("data", v_params.elen),
            ("mask", v_params.bytes_in_elen),
        ]


class VectorXRSLayout(RSLayouts):
    """Layout to describe scalar RS in vector func block"""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        super().__init__(gen_params, rs_entries_bits=rs_entries_bits)
        rs_interface = gen_params.get(RSInterfaceLayouts, rs_entries_bits=rs_entries_bits)

        self.data_layout: LayoutLike = layout_subset(
            rs_interface.data_layout,
            fields={
                "rp_s1",
                "rp_s2",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "s1_val",
                "s2_val",
                "imm",
                "imm2",
            },
        )

        self.insert_in: LayoutLike = [("rs_data", self.data_layout), ("rs_entry_id", rs_entries_bits)]
        self.take_out: LayoutLike = self.data_layout


class VectorStatusUnitLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue = layout_subset
