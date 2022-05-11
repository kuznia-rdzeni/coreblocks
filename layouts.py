from genparams import GenParams

class SchedulerLayouts:
    def __init__(self, gen_params : GenParams):
        self.reg_alloc_in = [
            ('rlog_1', gen_params.log_regs_bits),
            ('rlog_2', gen_params.log_regs_bits),
            ('rlog_out', gen_params.log_regs_bits)
        ]
        self.reg_alloc_out = self.renaming_in = [
            ('rlog_1', gen_params.log_regs_bits),
            ('rlog_2', gen_params.log_regs_bits),
            ('rlog_out', gen_params.log_regs_bits),
            ('rphys_out', gen_params.phys_regs_bits)
        ]
        self.renaming_out = [
            ('rphys_1', gen_params.phys_regs_bits),
            ('rphys_2', gen_params.phys_regs_bits),
            ('rlog_out', gen_params.log_regs_bits),
            ('rphys_out', gen_params.phys_regs_bits)
        ]
        self.rat_rename_in = [
            ('rlog_1', gen_params.log_regs_bits),
            ('rlog_2', gen_params.log_regs_bits),
            ('rlog_out', gen_params.log_regs_bits),
            ('rphys_out', gen_params.phys_regs_bits)
        ]
        self.rat_rename_out = [
            ('rphys_1', gen_params.phys_regs_bits),
            ('rphys_2', gen_params.phys_regs_bits)
        ]
        self.instr_layout = [
            ('rlog_1', gen_params.log_regs_bits),
            ('rlog_2', gen_params.log_regs_bits),
            ('rlog_out', gen_params.log_regs_bits)
        ]