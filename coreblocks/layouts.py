from coreblocks.genparams import GenParams
from coreblocks.isa import *

__all__ = [
    "SchedulerLayouts",
    "ROBLayouts",
    "CommonLayouts",
    "FetchLayouts",
    "DecodeLayouts",
    "FuncUnitLayouts",
    "RSLayouts",
    "RFLayouts",
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
        ]
        self.reg_alloc_out = self.renaming_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("regs_p", [("rp_dst", gen_params.phys_regs_bits)]),
            ("imm", gen_params.isa.xlen),
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
        ]
        self.rob_allocate_out = self.rs_select_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("imm", gen_params.isa.xlen),
        ]
        self.rs_select_out = self.rs_insert_in = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("rs_entry_id", gen_params.rs_entries_bits),
            ("imm", gen_params.isa.xlen),
        ]


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


class RSLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.data_layout = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
        ]

        self.insert_in = [("rs_data", self.data_layout), ("rs_entry_id", gen_params.rs_entries_bits)]

        self.select_out = [("rs_entry_id", gen_params.rs_entries_bits)]

        self.update_in = [("tag", gen_params.phys_regs_bits), ("value", gen_params.isa.xlen)]

        self.take_in = [("rs_entry_id", gen_params.rs_entries_bits)]

        self.take_out = [
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
        ]

        self.get_ready_list_out = [("ready_list", 2**gen_params.rs_entries_bits)]


class FetchLayouts:
    def __init__(self, gen_params: GenParams):
        self.raw_instr = [
            ("data", gen_params.isa.ilen),
        ]


class DecodeLayouts:
    def __init__(self, gen: GenParams):
        common = gen.get(CommonLayouts)
        self.decoded_instr = [
            ("opcode", Opcode),
            ("illegal", 1),
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("imm", gen.isa.xlen),
        ]


class FuncUnitLayouts:
    def __init__(self, gen: GenParams):
        common = gen.get(CommonLayouts)

        self.issue = [
            ("s1_val", gen.isa.xlen),
            ("s2_val", gen.isa.xlen),
            ("rp_dst", gen.phys_regs_bits),
            ("rob_id", gen.rob_entries_bits),
            ("exec_fn", common.exec_fn),
        ]

        self.accept = [
            ("rob_id", gen.rob_entries_bits),
            ("result", gen.isa.xlen),
            ("rp_dst", gen.phys_regs_bits),
        ]
