from coreblocks.params import GenParams, OpType, Funct7, Funct3, Opcode
from coreblocks.utils.utils import layout_subset

__all__ = [
    "SchedulerLayouts",
    "ROBLayouts",
    "CommonLayouts",
    "FetchLayouts",
    "DecodeLayouts",
    "FuncUnitLayouts",
    "RSInterfaceLayouts",
    "RSLayouts",
    "RFLayouts",
    "UnsignedMulUnitLayouts",
    "RATLayouts",
    "LSULayouts",
    "CSRLayouts",
]


class CommonLayouts:
    def __init__(self, gen_params: GenParams):
        self.exec_fn = [
            ("op_type", OpType),
            ("funct3", Funct3),
            ("funct7", Funct7),
        ]

        self.regs_l = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s1_v", 1),
            ("rl_s2", gen_params.isa.reg_cnt_log),
            ("rl_s2_v", 1),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("rl_dst_v", 1),
        ]

        self.regs_p = [
            ("rp_dst", gen_params.phys_regs_bits),
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
        ]


class SchedulerLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.reg_alloc_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]
        self.reg_alloc_out = self.renaming_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("regs_p", [("rp_dst", gen_params.phys_regs_bits)]),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]
        self.renaming_out = self.rob_allocate_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            (
                "regs_l",
                [
                    ("rl_dst", gen_params.isa.reg_cnt_log),
                    ("rl_dst_v", 1),
                ],
            ),
            ("regs_p", common.regs_p),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]
        self.rob_allocate_out = self.rs_select_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]
        self.rs_select_out = self.rs_insert_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("rs_selected", gen_params.rs_number_bits),
            ("rs_entry_id", gen_params.rs_entries_bits),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]
        self.free_rf_layout = [("reg_id", gen_params.phys_regs_bits)]


class RFLayouts:
    def __init__(self, gen_params: GenParams):
        self.rf_read_in = self.rf_free = [("reg_id", gen_params.phys_regs_bits)]
        self.rf_read_out = [("reg_val", gen_params.isa.xlen), ("valid", 1)]
        self.rf_write = [("reg_id", gen_params.phys_regs_bits), ("reg_val", gen_params.isa.xlen)]


class RATLayouts:
    def __init__(self, gen_params: GenParams):
        self.rat_rename_in = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s2", gen_params.isa.reg_cnt_log),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]
        self.rat_rename_out = [("rp_s1", gen_params.phys_regs_bits), ("rp_s2", gen_params.phys_regs_bits)]

        self.rat_commit_in = [("rl_dst", gen_params.isa.reg_cnt_log), ("rp_dst", gen_params.phys_regs_bits)]
        self.rat_commit_out = [("old_rp_dst", gen_params.phys_regs_bits)]


class ROBLayouts:
    def __init__(self, gen_params: GenParams):
        self.data_layout = [
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]

        self.id_layout = [
            ("rob_id", gen_params.rob_entries_bits),
        ]

        self.internal_layout = [
            ("rob_data", self.data_layout),
            ("done", 1),
        ]

        self.retire_layout = [("rob_data", self.data_layout), ("rob_id", gen_params.rob_entries_bits)]


class RSInterfaceLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.data_layout = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_s1_reg", gen_params.phys_regs_bits),
            ("rp_s2_reg", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]

        self.select_out = [("rs_entry_id", gen_params.rs_entries_bits)]

        self.insert_in = [("rs_data", self.data_layout), ("rs_entry_id", gen_params.rs_entries_bits)]

        self.update_in = [("tag", gen_params.phys_regs_bits), ("value", gen_params.isa.xlen)]


class RSLayouts:
    def __init__(self, gen_params: GenParams):
        rs_interface = gen_params.get(RSInterfaceLayouts)

        self.data_layout = layout_subset(
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
                "pc",
            },
        )

        self.insert_in = [("rs_data", self.data_layout), ("rs_entry_id", gen_params.rs_entries_bits)]

        self.select_out = rs_interface.select_out

        self.update_in = rs_interface.update_in

        self.take_in = [("rs_entry_id", gen_params.rs_entries_bits)]

        self.take_out = layout_subset(
            rs_interface.data_layout,
            fields={
                "s1_val",
                "s2_val",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "imm",
                "pc",
            },
        )

        self.get_ready_list_out = [("ready_list", 2**gen_params.rs_entries_bits)]


class FetchLayouts:
    def __init__(self, gen_params: GenParams):
        self.raw_instr = [
            ("data", gen_params.isa.ilen),
            ("pc", gen_params.isa.xlen),
        ]

        self.branch_verify = [
            ("next_pc", gen_params.isa.xlen),
        ]


class DecodeLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.decoded_instr = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("imm", gen_params.isa.xlen),
            ("csr", gen_params.isa.csr_alen),
            ("pc", gen_params.isa.xlen),
        ]


class FuncUnitLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)

        self.issue = [
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("imm", gen_params.isa.xlen),
            ("pc", gen_params.isa.xlen),
        ]

        self.accept = [
            ("rob_id", gen_params.rob_entries_bits),
            ("result", gen_params.isa.xlen),
            ("rp_dst", gen_params.phys_regs_bits),
        ]


class UnsignedMulUnitLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue = [
            ("i1", gen_params.isa.xlen),
            ("i2", gen_params.isa.xlen),
        ]

        self.accept = [
            ("o", 2 * gen_params.isa.xlen),
        ]


class LSULayouts:
    def __init__(self, gen_params: GenParams):
        rs_interface = gen_params.get(RSInterfaceLayouts)
        self.rs_data_layout = layout_subset(
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
            },
        )

        self.rs_insert_in = [("rs_data", self.rs_data_layout), ("rs_entry_id", gen_params.rs_entries_bits)]

        self.rs_select_out = rs_interface.select_out

        self.rs_update_in = rs_interface.update_in

        self.commit = [
            ("rob_id", gen_params.rob_entries_bits),
        ]


class CSRLayouts:
    def __init__(self, gen_params: GenParams):
        self.read = [
            ("data", gen_params.isa.xlen),
            ("read", 1),
            ("written", 1),
        ]

        self.write = [("data", gen_params.isa.xlen)]

        self._fu_read = [("data", gen_params.isa.xlen)]
        self._fu_write = [("data", gen_params.isa.xlen)]

        rs_interface = gen_params.get(RSInterfaceLayouts)
        self.rs_data_layout = layout_subset(
            rs_interface.data_layout,
            fields={
                "rp_s1",
                "rp_s1_reg",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "s1_val",
                "imm",
                "csr",
            },
        )

        self.rs_insert_in = [("rs_data", self.rs_data_layout), ("rs_entry_id", gen_params.rs_entries_bits)]

        self.rs_select_out = rs_interface.select_out

        self.rs_update_in = rs_interface.update_in
