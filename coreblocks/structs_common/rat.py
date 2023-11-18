from amaranth import *
from transactron import Method, def_method, TModule
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
        m = TModule()

        @def_method(m, self.rename)
        def _(rp_dst: Value, rl_dst: Value, rl_s1: Value, rl_s2: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"rp_s1": self.entries[rl_s1], "rp_s2": self.entries[rl_s2]}

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
        m = TModule()

        @def_method(m, self.commit)
        def _(rp_dst: Value, rl_dst: Value, side_fx: Value):
            with m.If(side_fx):
                m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"old_rp_dst": self.entries[rl_dst]}

        return m
