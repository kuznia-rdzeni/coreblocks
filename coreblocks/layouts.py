from coreblocks.genparams import GenParams

__all__ = ["SchedulerLayouts", "ROBLayouts"]


class SchedulerLayouts:
    def __init__(self, gen_params: GenParams):
        self.reg_alloc_in = [
            ("rl_s1", gen_params.isa.xlen_log),
            ("rl_s2", gen_params.isa.xlen_log),
            ("rl_dst", gen_params.isa.xlen_log),
        ]
        self.reg_alloc_out = self.renaming_in = [
            ("rl_s1", gen_params.isa.xlen_log),
            ("rl_s2", gen_params.isa.xlen_log),
            ("rl_dst", gen_params.isa.xlen_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]
        self.renaming_out = self.rob_allocate_in = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rl_dst", gen_params.isa.xlen_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]
        self.rob_allocate_out = [
            ("rp_s1", gen_params.phys_regs_bits),
            ("rp_s2", gen_params.phys_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
        ]
        self.instr_layout = [
            ("rl_s1", gen_params.isa.xlen_log),
            ("rl_s2", gen_params.isa.xlen_log),
            ("rl_dst", gen_params.isa.xlen_log),
        ]


class RATLayouts:
    def __init__(self, gen_params: GenParams):
        self.rat_rename_in = [
            ("rl_s1", gen_params.isa.xlen_log),
            ("rl_s2", gen_params.isa.xlen_log),
            ("rl_dst", gen_params.isa.xlen_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]
        self.rat_rename_out = [("rp_s1", gen_params.phys_regs_bits), ("rp_s2", gen_params.phys_regs_bits)]


class ROBLayouts:
    def __init__(self, gen_params: GenParams):
        self.data_layout = [
            ("rl_dst", gen_params.isa.xlen_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]

        self.id_layout = [
            ("rob_id", gen_params.rob_entries_bits),
        ]

        self.internal_layout = [
            ("rob_data", self.data_layout),
            ("done", 1),
        ]
