from amaranth import *

from coreblocks.transactions.core import Method, Transaction


class Retirement(Elaboratable):
    def __init__(self, rob_retire: Method, r_rat_put: Method, free_rf_put: Method):
        self.rob_retire = rob_retire
        self.rat_put = r_rat_put
        self.free_rf_put = free_rf_put

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            rob_entry = self.rob_retire(m)

            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.rat_put(m, {"rl_dst": rob_entry.rl_dst, "rp_dst": rob_entry.rp_dst})

            # put old rl_dst to free RF list
            with m.If(rat_out.old_rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rat_out.old_rp_dst)

        return m
