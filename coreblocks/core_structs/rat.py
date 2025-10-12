from amaranth import *
from amaranth.lib.data import ArrayLayout
from transactron import Method, Transaction, def_method, TModule
from coreblocks.interface.layouts import RATLayouts
from coreblocks.params import GenParams

__all__ = ["RRAT"]


class RRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params

        storage_layout = ArrayLayout(gen_params.phys_regs_bits, gen_params.isa.reg_cnt)
        self.entries = Signal(storage_layout, init=[rl for rl in range(gen_params.isa.reg_cnt)])

        layouts = gen_params.get(RATLayouts)
        self.commit = Method(i=layouts.rrat_commit_in, o=layouts.rrat_commit_out)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.commit)
        def _(rp_dst: Value, rl_dst: Value):
            with m.If(rl_dst != 0):
                m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"old_rp_dst": self.entries[rl_dst]}

        return m
