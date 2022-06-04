from coreblocks.genparams import GenParams

__all__ = ["SchedulerLayouts", "ROBLayouts"]


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
        self.rob_allocate_out = self.rs_select_in = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("opcode", gen_params.isa.ilen),
        ]
        self.rs_select_out = self.rs_insert_in = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("opcode", gen_params.isa.ilen),
            ("rs_entry_id", gen_params.rs_entries_bits),
        ]
        self.instr_layout = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s2", gen_params.isa.reg_cnt_log),
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("opcode", gen_params.isa.ilen),
        ]


class RFLayouts:
    def __init__(self, gen_params: GenParams):
        self.rf_read_in = self.rf_free = [("reg_id", gen_params.phys_regs_bits)]
        self.rf_read_out = [("reg_val", gen_params.isa.xlen_log), ("valid", 1)]
        self.rf_write = [("reg_id", gen_params.phys_regs_bits), ("reg_val", gen_params.isa.xlen_log)]


class RSLayouts:
    def __init__(self, gen_params: GenParams):
        self.rs_allocate_out = [("entry_id", gen_params.rs_entries_bits)]
        self.rs_insert_in = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("opcode", gen_params.isa.ilen),
            ("rs_entry_id", gen_params.rs_entries_bits),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
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
