from amaranth import *

from coreblocks.transactions.core import Method, Transaction, ModuleX
from coreblocks.params.genparams import GenParams
from coreblocks.structs_common.csr_generic import CSRAddress, DoubleCounterCSR


class Retirement(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        rob_retire: Method,
        r_rat_commit: Method,
        free_rf_put: Method,
        rf_free: Method,
        lsu_commit: Method
    ):
        self.rob_retire = rob_retire
        self.r_rat_commit = r_rat_commit
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.lsu_commit = lsu_commit

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)

    def elaborate(self, platform):
        m = ModuleX()

        m.submodules.instret_csr = self.instret_csr

        with Transaction().body(m):
            rob_entry = self.rob_retire(m)

            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit(m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst)

            self.rf_free(m, rat_out.old_rp_dst)
            self.lsu_commit(m, rob_id=rob_entry.rob_id)

            # put old rp_dst to free RF list
            with m.If(rat_out.old_rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rat_out.old_rp_dst)

            self.instret_csr.increment(m)

        return m
