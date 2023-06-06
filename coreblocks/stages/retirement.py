from amaranth import *

from coreblocks.transactions.core import Method, Transaction, TModule, def_method
from coreblocks.params.genparams import GenParams
from coreblocks.structs_common.csr_generic import CSRAddress, DoubleCounterCSR


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
    ):
        self.gen_params = gen_params
        self.rob_peek = rob_peek
        self.rob_retire = rob_retire
        self.r_rat_commit = r_rat_commit
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.precommit = precommit

        self.stall = Method()
        self.unstall = Method()

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.instret_csr = self.instret_csr

        # describes whether we can stall - asserted only for one cycle after a successfull rob_retire call
        can_stall = Signal()
        m.d.sync += can_stall.eq(0)
        # stall request from outside
        stall_req = Signal()
        imm_stall_req = Signal()
        # if we just retired an instruction (means no precommit was made on the current one) and
        # stall_req is asserted that's when we should really stall
        stall_cond = can_stall & (stall_req | imm_stall_req)

        @def_method(m, self.stall, ready=can_stall)
        def _():
            m.d.sync += stall_req.eq(1)
            m.d.comb += imm_stall_req.eq(1)

        @def_method(m, self.unstall, ready=stall_req)
        def _():
            m.d.sync += stall_req.eq(0)

        precommit_trans = Transaction(name="precommit")
        retire_trans = Transaction(name="retire")

        with precommit_trans.body(m, request=~stall_cond):
            # TODO: do we prefer single precommit call per instruction?
            # If so, the precommit method should send an acknowledge signal here.
            # Just calling once is not enough, because the insn might not be in relevant unit yet.
            rob_entry = self.rob_peek(m)
            self.precommit(m, rob_id=rob_entry.rob_id)

        with retire_trans.body(m, request=~stall_cond):
            rob_entry = self.rob_retire(m)
            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit(m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst)

            self.rf_free(m, rat_out.old_rp_dst)

            # put old rp_dst to free RF list
            with m.If(rat_out.old_rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rat_out.old_rp_dst)

            self.instret_csr.increment(m)
            m.d.sync += can_stall.eq(1)

        self.stall.add_conflict(self.unstall)
        self.stall.schedule_before(precommit_trans)
        self.stall.schedule_before(retire_trans)

        return m
