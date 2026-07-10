from amaranth import *
from transactron import Method, Methods, def_method, TModule, def_methods
from coreblocks.interface.layouts import RATLayouts
from coreblocks.params import GenParams

__all__ = ["RRAT"]


class RRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = gen_params.get(RATLayouts)
        self.entries = Signal(layouts.entries_shape)

        self.commit = Methods(gen_params.retirement_superscalarity, i=layouts.rrat_commit_in, o=layouts.rrat_commit_out)
        self.peek = Method(o=layouts.rrat_peek_out)

    def elaborate(self, platform):
        m = TModule()

        @def_methods(m, self.commit)
        def _(i: int, rp_dst: Value, rl_dst: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)

            old_rp_dst = Signal(self.gen_params.phys_regs_bits)
            m.d.av_comb += old_rp_dst.eq(self.entries[rl_dst])
            for j in range(i):
                with m.If(self.commit[j].run & (self.commit[j].data_in.rl_dst == rl_dst)):
                    m.d.av_comb += old_rp_dst.eq(self.commit[j].data_in.rp_dst)
            return {"old_rp_dst": old_rp_dst}

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            return {"entries": self.entries}

        return m
