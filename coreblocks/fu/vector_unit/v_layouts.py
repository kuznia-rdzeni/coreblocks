from amaranth.utils import *
from coreblocks.params import *
from coreblocks.utils._typing import LayoutLike
from coreblocks.utils import layout_subset, layout_difference


class VectorRegisterBankLayouts:
    def __init__(self, gen_params: GenParams):
        v_params = gen_params.v_params
        self.read_resp = [("data", v_params.elen)]

        self.write = [
            ("addr", range(v_params.elens_in_bank)),
            ("data", v_params.elen),
            ("valid_mask", v_params.bytes_in_elen),
        ]
        self.write_scalar = [("value", v_params.elen)]

        self.initialise = []


class VRFFragmentLayouts:
    def __init__(self, gen_params: GenParams):
        v_params = gen_params.v_params
        self.read_req = [("vrp_id", v_params.vrp_count_bits), ("addr", range(v_params.elens_in_bank))]

        self.read_resp_i = [("vrp_id", v_params.vrp_count_bits)]
        self.read_resp_o = [("data", v_params.elen)]

        self.write = [
            ("vrp_id", v_params.vrp_count_bits),
            ("addr", range(v_params.elens_in_bank)),
            ("data", v_params.elen),
            ("valid_mask", v_params.bytes_in_elen),
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


class VectorVRSLayout(RSLayouts):
    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        super().__init__(gen_params, rs_entries_bits=rs_entries_bits)
        common = gen_params.get(CommonLayouts)
        common_vector = VectorCommonLayouts(gen_params)

        # TODO check if all bits are needed
        # TODO add prechecking which registers are used and wait only on these
        self.data_layout: LayoutLike = [
            ("rp_s1", common.p_register_entry),
            ("rp_s2", common.p_register_entry),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("vtype", common_vector.vtype),
            ("rp_s3", common.p_register_entry),
            ("rp_v0", [("id", gen_params.phys_regs_bits)]),
            ("rp_s1_rdy", 1),
            ("rp_s2_rdy", 1),
            ("rp_s3_rdy", 1),
            ("rp_v0_rdy", 1),
        ]

        self.insert_in: LayoutLike = [("rs_data", self.data_layout), ("rs_entry_id", rs_entries_bits)]
        self.take_out: LayoutLike = self.data_layout


class VectorCommonLayouts:
    def __init__(self, gen_params: GenParams):
        # TODO optimisation use 16 bits for VL
        self.vtype = [("lmul", LMUL), ("sew", SEW), ("ta", 1), ("ma", 1), ("vl", gen_params.isa.xlen)]


class VectorFrontendLayouts:
    def __init__(self, gen_params: GenParams):
        v_params = gen_params.v_params
        common = gen_params.get(CommonLayouts)
        common_vector = VectorCommonLayouts(gen_params)
        self.vtype = common_vector.vtype

        self.verification_in = self.verification_out = self.status_in = [
            ("rp_s1", common.p_register_entry),
            ("rp_s2", common.p_register_entry),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
        ]

        self.status_out = self.translator_in = layout_difference(self.status_in, fields={"imm2"}) + [
            ("vtype", self.vtype)
        ]
        self.translator_inner = layout_difference(self.translator_in, fields={"imm"})
        self.translator_out = self.translator_inner + [
            ("rp_s3", common.p_register_entry),
            ("rp_v0", [("id", gen_params.phys_regs_bits)]),
        ]
        self.alloc_rename_out = self.alloc_rename_in = self.translator_out
        self.get_vill = [("vill", 1)]
        self.get_vstart = [("vstart", v_params.vstart_bits)]
        self.translator_report_multiplier = [("mult", 4), ("rob_id", gen_params.rob_entries_bits)]

        self.instr_to_mem = [
            ("rp_s2", common.p_register_entry),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("vtype", self.vtype),
            ("rp_s3", common.p_register_entry),
            ("rp_v0", [("id", gen_params.phys_regs_bits)]),
        ]

        self.instr_to_vvrs = [
            ("rp_s1", common.p_register_entry),
            ("rp_s2", common.p_register_entry),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("vtype", self.vtype),
            ("rp_s3", common.p_register_entry),
            ("rp_v0", [("id", gen_params.phys_regs_bits)]),
        ]


class VectorAluLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        v_params = gen_params.v_params
        self.alu_in = [("s1", v_params.elen), ("s2", v_params.elen), ("exec_fn", common.exec_fn), ("eew", EEW)]

        self.alu_out = [("dst_val", v_params.elen)]


class VectorBackendLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        common_vector = gen_params.get(VectorCommonLayouts)
        frontend = VectorFrontendLayouts(gen_params)
        v_params = gen_params.v_params

        self.executor_in = self.vvrs_out = self.vvrs_in = frontend.instr_to_vvrs

        self.len_getter_out = [
            ("elens_len", gen_params.v_params.elens_in_bank_bits),
            ("last_mask", v_params.bytes_in_elen),
        ]
        self.needed_regs_out = [("s1_needed", 1), ("s2_needed", 1), ("s3_needed", 1), ("v0_needed", 1)]
        self.downloader_in = [
            ("s1", gen_params.phys_regs_bits),
            ("s1_needed", 1),
            ("s2", gen_params.phys_regs_bits),
            ("s2_needed", 1),
            ("s3", gen_params.phys_regs_bits),
            ("s3_needed", 1),
            ("v0", gen_params.phys_regs_bits),
            ("v0_needed", 1),
            ("elens_len", v_params.elens_in_bank_bits),
            ("last_mask", v_params.bytes_in_elen),
        ]

        self.data_splitter_in = self.downloader_data_out = [
            ("s1", v_params.elen),
            ("s2", v_params.elen),
            ("s3", v_params.elen),
            ("v0", v_params.elen),
            ("elen_index", v_params.elens_in_bank),
            ("last_mask", v_params.bytes_in_elen),
        ]
        self.data_splitter_init_in = [
            ("vtype", common_vector.vtype),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
        ]

        self.uploader_result_in = self.fu_data_out = [("dst_val", v_params.elen)]
        self.uploader_init_in = [
            ("vrp_id", gen_params.phys_regs_bits),
            ("ma", 1),
            ("elens_len", v_params.elens_in_bank_bits),
        ]
        self.mask_extractor_out = self.uploader_mask_in = [("mask", v_params.bytes_in_elen)]
        self.uploader_old_dst_in = [("old_dst_val", v_params.elen)]

        self.mask_extractor_in = [
            ("v0", v_params.elen),
            ("elen_index", v_params.elens_in_bank),
            ("eew", EEW),
            ("vm", 1),
            ("last_mask", v_params.bytes_in_elen),
        ]

        self.ender_init_in = [
            ("rob_id", gen_params.rob_entries_bits),
            ("rp_dst", common.p_register_entry),
        ]
        self.ender_report_mult = [
            ("rob_id", gen_params.rob_entries_bits),
            ("mult", 4),
        ]


class VectorRetirementLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.report_end = [
            ("rob_id", gen_params.rob_entries_bits),
            ("rp_dst", common.p_register_entry),
        ]

class VectorLSULayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        common_vector = VectorCommonLayouts(gen_params)
        retirement = gen_params.get(RetirementLayouts)
        self.rs_entries_bits = 0

        rs_interface = gen_params.get(RSInterfaceLayouts, rs_entries_bits=self.rs_entries_bits)
        self.rs_data_layout = [
            ("rp_s2", common.p_register_entry),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("vtype", common_vector.vtype),
            ("rp_s3", common.p_register_entry),
            ("rp_v0", [("id", gen_params.phys_regs_bits)]),
            ("rp_s2_rdy", 1),
            ("rp_s3_rdy", 1),
            ("rp_v0_rdy", 1),
        ]

        self.rs_insert_in = [("rs_data", self.rs_data_layout), ("rs_entry_id", self.rs_entries_bits)]

        self.rs_select_out = rs_interface.select_out

        self.rs_update_in = rs_interface.update_in

        self.precommit = retirement.precommit
