from amaranth import *

from coreblocks.transactions.core import Method, Transaction, TModule
from coreblocks.params.genparams import GenParams
from coreblocks.structs_common.csr_generic import CSRAddress, DoubleCounterCSR
from coreblocks.stages.int_coordinator import InterruptCoordinator


class Retirement(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        rob_peek: Method,
        rob_retire: Method,
        r_rat_commit: Method,
        free_rf_put: Method,
        rf_free: Method,
        precommit: Method,
        int_coordinator: InterruptCoordinator
    ):
        self.gen_params = gen_params
        self.rob_peek = rob_peek
        self.rob_retire = rob_retire
        self.r_rat_commit = r_rat_commit
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.precommit = precommit
        self.int_coordinator = int_coordinator

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.instret_csr = self.instret_csr

        with Transaction().body(m):
            # TODO: do we prefer single precommit call per instruction?
            # If so, the precommit method should send an acknowledge signal here.
            # Just calling once is not enough, because the insn might not be in relevant unit yet.
            rob_entry = self.rob_peek(m)
            self.precommit(m, rob_id=rob_entry.rob_id)

        with Transaction().body(m, request=self.int_coordinator.allow_retirement):
            # look up instruction without actually retiring it
            self.lookup = Record.like(self.rob_retire.data_out)
            m.d.comb += self.lookup.eq(self.rob_retire.data_out)
            with m.If(self.lookup.interrupt):
                self.int_coordinator.trigger(m, self.lookup.rob_data.pc)
            with m.Else():
                rob_entry = self.rob_retire(m)
                # set rl_dst -> rp_dst in R-RAT
                rat_out = self.r_rat_commit(m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst)

                self.rf_free(m, rat_out.old_rp_dst)

                # put old rp_dst to free RF list
                with m.If(rat_out.old_rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                    self.free_rf_put(m, rat_out.old_rp_dst)

                self.instret_csr.increment(m)

        return m
