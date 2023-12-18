from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.isa import ExceptionCause
from coreblocks.params.keys import GenericCSRRegistersKey
from coreblocks.params.layouts import CommonLayoutFields

from transactron.core import Method, Transaction, TModule
from coreblocks.params.genparams import GenParams
from coreblocks.structs_common.csr_generic import CSRAddress, DoubleCounterCSR
from transactron.lib.connectors import Forwarder


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
        exception_cause_clear: Method,
        frat_rename: Method,
        fetch_continue: Method,
        fetch_stall: Method,
        instr_decrement: Method,
        trap_entry: Method,
    ):
        self.gen_params = gen_params
        self.rob_peek = rob_peek
        self.rob_retire = rob_retire
        self.r_rat_commit = r_rat_commit
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.precommit = precommit
        self.exception_cause_get = exception_cause_get
        self.exception_cause_clear = exception_cause_clear
        self.rename = frat_rename
        self.fetch_continue = fetch_continue
        self.fetch_stall = fetch_stall
        self.instr_decrement = instr_decrement
        self.trap_entry = trap_entry

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)

    def elaborate(self, platform):
        m = TModule()

        m_csr = self.gen_params.get(DependencyManager).get_dependency(GenericCSRRegistersKey()).m_mode
        m.submodules.instret_csr = self.instret_csr

        side_fx = Signal(reset=1)
        side_fx_comb = Signal()
        last_commited = Signal()

        m.d.comb += side_fx_comb.eq(side_fx)

        # Use Forwarders for calling those methods, because we don't want them to block
        # Retirement Transaction (because of un-readiness) during normal operation (both
        # methods are unused when not handling exceptions)
        fields = self.gen_params.get(CommonLayoutFields)
        m.submodules.frat_fix = frat_fix = Forwarder([fields.rl_dst, fields.rp_dst])
        m.submodules.fetch_continue_fwd = fetch_continue_fwd = Forwarder([fields.pc])

        with Transaction().body(m):
            # TODO: do we prefer single precommit call per instruction?
            # If so, the precommit method should send an acknowledge signal here.
            # Just calling once is not enough, because the insn might not be in relevant unit yet.
            rob_entry = self.rob_peek(m)
            self.precommit(m, rob_id=rob_entry.rob_id, side_fx=side_fx)

        with Transaction().body(m):
            rob_entry = self.rob_retire(m)

            with m.If(rob_entry.exception & side_fx):
                # Start flushing the core
                m.d.sync += side_fx.eq(0)
                m.d.comb += side_fx_comb.eq(0)
                self.fetch_stall(m)

                cause_register = self.exception_cause_get(m)

                cause_entry = Signal(self.gen_params.isa.xlen)

                with m.If(cause_register.cause == ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT):
                    # Async interrupts are inserted only by JumpBranchUnit and conditionally by MRET and CSR operations.
                    # The PC field is set to address of instruction to resume from interrupt (e.g. for jumps it is
                    # a jump result).
                    # Instruction that reported interrupt is the last one that is commited.
                    m.d.comb += side_fx_comb.eq(1)
                    # Another flag is needed to resume execution if it was the last instruction in core
                    m.d.comb += last_commited.eq(1)

                    # TODO: set correct interrupt id (from InterruptController) when multiple interrupts are supported
                    # Set MSB - the Interrupt bit
                    m.d.comb += cause_entry.eq(1 << (self.gen_params.isa.xlen - 1))
                with m.Else():
                    m.d.comb += cause_entry.eq(cause_register.cause)

                m_csr.mcause.write(m, cause_entry)
                m_csr.mepc.write(m, cause_register.pc)

                self.trap_entry(m)

            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit(
                m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst, side_fx=side_fx
            )

            rp_freed = Signal(self.gen_params.phys_regs_bits)
            with m.If(side_fx_comb):
                m.d.av_comb += rp_freed.eq(rat_out.old_rp_dst)
                self.instret_csr.increment(m)
            with m.Else():
                m.d.av_comb += rp_freed.eq(rob_entry.rob_data.rp_dst)
                # free the phys_reg with computed value and restore old reg into FRAT as well
                # FRAT calls are in a separate transaction to avoid locking the rename method
                frat_fix.write(m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rat_out.old_rp_dst)

            self.rf_free(m, rp_freed)

            # put old rp_dst to free RF list
            with m.If(rp_freed):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rp_freed)

            core_empty = self.instr_decrement(m)
            # cycle when fetch_stop is called, is the last cycle when new instruction can be fetched.
            # in this case, counter will be incremented and result correct (non-empty).
            with m.If((~side_fx_comb | last_commited) & core_empty):
                # Resume core operation from exception handler

                # mtvec without mode is [mxlen-1:2], mode is two last bits. Only direct mode is supported
                resume_pc = m_csr.mtvec.read(m) & ~(0b11)
                fetch_continue_fwd.write(m, pc=resume_pc)

                # Release pending trap state - allow accepting new reports
                self.exception_cause_clear(m)

                m.d.sync += side_fx.eq(1)

        with Transaction().body(m):
            data = frat_fix.read(m)
            self.rename(m, rl_s1=0, rl_s2=0, rl_dst=data["rl_dst"], rp_dst=data["rp_dst"])

        # Fetch continue cannot be executed at the same time as fetch_stall, it causes fetcher to break
        # Confilct can't be defined implicitly via Method.conflict, - it causes preformace loss, because of
        # transaction locking (fetch_stop is only under If in common Transaction).
        # Define conflict with priority to fetch_stall here. It is correct, because retirement is the only place
        # where fetch_stall is called.
        with Transaction().body(m, request=~self.fetch_stall.run):
            pc = fetch_continue_fwd.read(m).pc
            self.fetch_continue(m, from_pc=0, next_pc=pc, resume_from_exception=1)

        return m
