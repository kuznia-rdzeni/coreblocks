from coreblocks.genparams import GenParams
from coreblocks.isa import *

__all__ = [
    "SchedulerLayouts",
    "ROBLayouts",
    "CommonLayouts",
    "FuncUnitLayouts",
]


class CommonLayouts:
    def __init__(self, gen_params: GenParams):
        self.exec_fn = [
            ("op_type", OpType),
            ("funct3", Funct3),
            ("funct7", Funct7),
        ]


class SchedulerLayouts:
    def __init__(self, gen_params: GenParams):
        self.reg_alloc_in = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s2", gen_params.isa.reg_cnt_log),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            # Note: using ilen here and in the following records is currently a placeholder
            ("opcode", gen_params.isa.ilen),
        ]
        self.reg_alloc_out = self.renaming_in = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s2", gen_params.isa.reg_cnt_log),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("rp_dst", gen_params.phys_regs_bits),
            ("opcode", gen_params.isa.ilen),
        ]
        self.renaming_out = self.rob_allocate_in = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("rp_dst", gen_params.phys_regs_bits),
            ("opcode", gen_params.isa.ilen),
        ]
        self.rob_allocate_out = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("opcode", gen_params.isa.ilen),
        ]
        self.instr_layout = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s2", gen_params.isa.reg_cnt_log),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("opcode", gen_params.isa.ilen),
        ]


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


class FuncUnitLayouts:
    def __init__(self, gen: GenParams):
        common = gen.get(CommonLayouts)

        self.issue = [
            ("rob_id", gen.rob_entries_bits),
            ("data1", gen.isa.xlen),
            ("data2", gen.isa.xlen),
            ("fn", common.exec_fn),
            ("rp_dst", gen.phys_regs_bits),
        ]

        self.accept = [
            ("rob_id", gen.rob_entries_bits),
            ("result", gen.isa.xlen),
            ("rp_dst", gen.phys_regs_bits),
        ]
