from amaranth import *
from transactron import Method, Methods, def_method, TModule, def_methods
from coreblocks.interface.layouts import RATLayouts
from coreblocks.params import GenParams

__all__ = ["FRAT", "RRAT"]


class FRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        layouts = gen_params.get(RATLayouts)
        self.rename = Method(i=layouts.frat_rename_in, o=layouts.frat_rename_out)

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
        self.entries = Signal(layouts.rat_array)

        self.commit = Methods(gen_params.retirement_superscalarity, i=layouts.rrat_commit_in, o=layouts.rrat_commit_out)
        self.peek = Methods(gen_params.retirement_superscalarity, i=layouts.rrat_peek_in, o=layouts.rrat_peek_out)

    def elaborate(self, platform):
        m = TModule()

        @def_methods(m, self.commit)
        def _(i: int, rp_dst: Value, rl_dst: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"old_rp_dst": self.peek[i](m, rl_dst)}

        @def_methods(m, self.peek)
        def _(i: int, rl_dst: Value):
            old_rp_dst = Signal(self.gen_params.phys_regs_bits)
            m.d.av_comb += old_rp_dst.eq(self.entries[rl_dst])
            for j in range(i):
                with m.If(self.commit[j].run & (self.commit[j].data_in.rl_dst == rl_dst)):
                    m.d.av_comb += old_rp_dst.eq(self.commit[j].data_in.rp_dst)
            return old_rp_dst

        return m
