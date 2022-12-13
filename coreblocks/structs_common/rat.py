from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.params import RATLayouts, GenParams

__all__ = ["FRAT", "RRAT"]


class FRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RATLayouts)
        self.rename_input_layout = layouts.rat_rename_in
        self.rename_output_layout = layouts.rat_rename_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        self.rename = Method(i=self.rename_input_layout, o=self.rename_output_layout)

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.rename)
        def _(arg):
            m.d.sync += self.entries[arg.rl_dst].eq(arg.rp_dst)
            return {"rp_s1": self.entries[arg.rl_s1], "rp_s2": self.entries[arg.rl_s2]}

        return m


class RRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RATLayouts)
        self.commit_input_layout = layouts.rat_commit_in
        self.commit_output_layout = layouts.rat_commit_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        self.commit = Method(i=self.commit_input_layout, o=self.commit_output_layout)

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.commit)
        def _(arg):
            m.d.sync += self.entries[arg.rl_dst].eq(arg.rp_dst)
            return {"old_rp_dst": self.entries[arg.rl_dst]}

        return m
