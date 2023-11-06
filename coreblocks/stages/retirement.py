from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.keys import GenericCSRRegistersKey

from transactron.core import Method, Transaction, TModule
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
        exception_cause_get: Method,
        frat_rename: Method,
    ):
        self.gen_params = gen_params
        self.rob_peek = rob_peek
        self.rob_retire = rob_retire
        self.r_rat_commit = r_rat_commit
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.precommit = precommit
        self.exception_cause_get = exception_cause_get
        self.rename = frat_rename

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.instret_csr = self.instret_csr

        side_fx = Signal(reset=1)

        with Transaction().body(m):
            # TODO: do we prefer single precommit call per instruction?
            # If so, the precommit method should send an acknowledge signal here.
            # Just calling once is not enough, because the insn might not be in relevant unit yet.
            rob_entry = self.rob_peek(m)
            self.precommit(m, rob_id=rob_entry.rob_id, side_fx=side_fx)

        with Transaction().body(m):
            rob_entry = self.rob_retire(m)

            # TODO: Trigger InterruptCoordinator (handle exception) when rob_entry.exception is set.
            with m.If(rob_entry.exception & side_fx):
                m.d.sync += side_fx.eq(0)
                # TODO: only set mcause/trigger IC if cause is actual exception and not e.g.
                # misprediction or pipeline flush after some fence.i or changing ISA
                mcause = self.gen_params.get(DependencyManager).get_dependency(GenericCSRRegistersKey()).mcause
                cause = self.exception_cause_get(m).cause
                entry = Signal(self.gen_params.isa.xlen)
                # MSB is exception bit
                m.d.comb += entry.eq(cause | (1 << (self.gen_params.isa.xlen - 1)))
                mcause.write(m, entry)

            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit(
                m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst, side_fx=side_fx
            )

            rp_freed = Signal(self.gen_params.phys_regs_bits)
            with m.If(side_fx):
                m.d.comb += rp_freed.eq(rat_out.old_rp_dst)
                self.instret_csr.increment(m)
            with m.Else():
                m.d.comb += rp_freed.eq(rob_entry.rob_data.rp_dst)
                # free the phys_reg with computed value and restore old reg into FRAT as well
                # TODO: are method priorities enough?
                self.rename(m, rl_s1=0, rl_s2=0, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rat_out.old_rp_dst)

            self.rf_free(m, rp_freed)

            # put old rp_dst to free RF list
            with m.If(rp_freed):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rp_freed)

        return m
