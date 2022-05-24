from .genparams import GenParams

__all__ = [
    "ROBLayouts",
]

class ROBLayouts:
    def __init__(self, gen_params: GenParams):
        self.data_layout = [
            ("rl_dst", gen_params.log_regs_bits),
            ("rp_dst", gen_params.phys_regs_bits),
        ]

        self.id_layout = [
            ("rob_id", gen_params.rob_entries_bits),
        ]

        self.internal_layout = [
            ("rob_data", self.data_layout),
            ("done", 1),
        ]

