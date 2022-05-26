from amaranth import *
from coreblocks.transactions import Method
from coreblocks.transactions.lib import def_method
from coreblocks.layouts import RATLayouts
from coreblocks.genparams import GenParams

__all__ = ["RAT"]


class RAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RATLayouts)
        self.input_layout = layouts.rat_rename_in
        self.output_layout = layouts.rat_rename_out

        self.entries = Array((Signal(self.gen_params.phys_regs_bits, reset=i) for i in range(32)))

        self.if_rename = Method(i=self.input_layout, o=self.output_layout)

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.if_rename)
        def _(arg):
            m.d.sync += self.entries[arg.rl_dst].eq(arg.rp_dst)
            return {"rp_s1": self.entries[arg.rl_s1], "rp_s2": self.entries[arg.rl_s2]}
        return m
