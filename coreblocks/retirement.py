from amaranth import *

from coreblocks.transactions.core import Method, Transaction
from coreblocks.genparams import GenParams
from coreblocks.layouts import RATLayouts


class Retirement(Elaboratable):
    def __init__(self, gen_params: GenParams, rob_retire: Method, r_rat_put: Method, free_rf_put: Method):
        self.layouts = gen_params.get(RATLayouts)

        self.rob_retire = rob_retire
        self.rat_put = r_rat_put
        self.free_rf_put = free_rf_put

    def elaborate(self, platform):
        m = Module()

        rat_in = Record(self.layouts.rat_commit_in)

        with Transaction().body(m):
            rob_entry = self.rob_retire(m)

            # set rl_dst -> rp_dst in R-RAT
            m.d.comb += rat_in.rl_dst.eq(rob_entry.rl_dst)
            m.d.comb += rat_in.rp_dst.eq(rob_entry.rp_dst)
            rat_out = self.rat_put(m, rat_in)
            # put old r1_dst to free RF list

            with m.If(rat_out.old_rp_dst):  # don't put r0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rat_out.old_rp_dst)

        return m
