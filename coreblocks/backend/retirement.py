from amaranth import *
from coreblocks.interface.layouts import RetirementLayouts

from transactron.core import Method, Transaction, TModule, def_method
from transactron.lib.simultaneous import condition
from transactron.utils.dependencies import DependencyContext
from transactron.lib.metrics import *

from coreblocks.params.genparams import GenParams
from coreblocks.arch import ExceptionCause
from coreblocks.interface.keys import CoreStateKey, GenericCSRRegistersKey, InstructionPrecommitKey
from coreblocks.priv.csr.csr_instances import CSRAddress, DoubleCounterCSR


class Retirement(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        rob_peek: Method,
        rob_retire: Method,
        r_rat_commit: Method,
        r_rat_peek: Method,
        free_rf_put: Method,
        rf_free: Method,
        exception_cause_get: Method,
        exception_cause_clear: Method,
        frat_rename: Method,
        fetch_continue: Method,
        instr_decrement: Method,
        trap_entry: Method,
        async_interrupt_cause: Method,
        ftq_commit: Method,
    ):
        self.gen_params = gen_params
        self.rob_peek = rob_peek
        self.rob_retire = rob_retire
        self.r_rat_commit = r_rat_commit
        self.r_rat_peek = r_rat_peek
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.exception_cause_get = exception_cause_get
        self.exception_cause_clear = exception_cause_clear
        self.rename = frat_rename
        self.fetch_continue = fetch_continue
        self.instr_decrement = instr_decrement
        self.trap_entry = trap_entry
        self.async_interrupt_cause = async_interrupt_cause
        self.ftq_commit = ftq_commit

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)
        self.perf_instr_ret = HwCounter("backend.retirement.retired_instr", "Number of retired instructions")
        self.perf_trap_latency = FIFOLatencyMeasurer(
            "backend.retirement.trap_latency",
            "Cycles spent flushing the core after a trap",
            slots_number=1,
            max_latency=2 * 2**gen_params.rob_entries_bits,
        )

        self.dependency_manager = DependencyContext.get()
        self.core_state = Method(o=self.gen_params.get(RetirementLayouts).core_state, nonexclusive=True)
        self.dependency_manager.add_dependency(CoreStateKey(), self.core_state)

        self.precommit = Method(o=self.gen_params.get(RetirementLayouts).precommit, nonexclusive=True)
        self.dependency_manager.add_dependency(InstructionPrecommitKey(), self.precommit)

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr_ret, self.perf_trap_latency]

        m_csr = self.dependency_manager.get_dependency(GenericCSRRegistersKey()).m_mode
        m.submodules.instret_csr = self.instret_csr

        side_fx = Signal(reset=1)

        def free_phys_reg(rp_dst: Value):
            # mark reg in Register File as free
            self.rf_free(m, rp_dst)
            # put to Free RF list
            with m.If(rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rp_dst)

        def retire_instr(rob_entry):
            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit(m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst)

            # free old rp_dst from overwritten R-RAT mapping
            free_phys_reg(rat_out.old_rp_dst)

            self.instret_csr.increment(m)
            self.perf_instr_ret.incr(m)

        def flush_instr(rob_entry):
            # get original rp_dst mapped to instruction rl_dst in R-RAT
            rat_out = self.r_rat_peek(m, rl_dst=rob_entry.rob_data.rl_dst)

            # free the "new" instruction rp_dst - result is flushed
            free_phys_reg(rob_entry.rob_data.rp_dst)

            # restore original rl_dst->rp_dst mapping in F-RAT
            self.rename(m, rl_s1=0, rl_s2=0, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rat_out.old_rp_dst)

        retire_valid = Signal()
        with Transaction().body(m) as validate_transaction:
            # Ensure that when exception is processed, correct entry is alredy in ExceptionCauseRegister
            rob_entry = self.rob_peek(m)
            ecr_entry = self.exception_cause_get(m)
            m.d.comb += retire_valid.eq(
                ~rob_entry.exception | (rob_entry.exception & ecr_entry.valid & (ecr_entry.rob_id == rob_entry.rob_id))
            )

        continue_pc_override = Signal()
        continue_pc = Signal(self.gen_params.isa.xlen)
        core_flushing = Signal()

        with m.FSM("NORMAL") as fsm:
            with m.State("NORMAL"):
                with Transaction().body(m, request=retire_valid) as retire_transaction:
                    rob_entry = self.rob_peek(m)
                    self.rob_retire(m)

                    core_empty = self.instr_decrement(m)

                    commit = Signal()

                    with m.If(rob_entry.exception):
                        self.perf_trap_latency.start(m)

                        cause_register = self.exception_cause_get(m)

                        cause_entry = Signal(self.gen_params.isa.xlen)

                        arch_trap = Signal(reset=1)

                        with m.If(cause_register.cause == ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT):
                            # Async interrupts are inserted only by JumpBranchUnit and conditionally by MRET and CSR
                            # The PC field is set to address of instruction to resume from interrupt (e.g. for jumps
                            # it is a jump result).
                            # Instruction that reported interrupt is the last one that is commited.
                            m.d.av_comb += commit.eq(1)

                            # Set MSB - the Interrupt bit
                            m.d.av_comb += cause_entry.eq(
                                (1 << (self.gen_params.isa.xlen - 1)) | self.async_interrupt_cause(m).cause
                            )
                        with m.Elif(cause_register.cause == ExceptionCause._COREBLOCKS_MISPREDICTION):
                            # Branch misprediction - commit jump, flush core and continue from correct pc.
                            m.d.av_comb += commit.eq(1)
                            # Do not modify trap related CSRs
                            m.d.av_comb += arch_trap.eq(0)

                            m.d.sync += continue_pc_override.eq(1)
                            m.d.sync += continue_pc.eq(cause_register.pc)
                        with m.Else():
                            # RISC-V synchronous exceptions - don't retire instruction that caused exception,
                            # and later resume from it.
                            # Value of ExceptionCauseRegister pc field is the instruction address.
                            m.d.av_comb += commit.eq(0)

                            m.d.av_comb += cause_entry.eq(cause_register.cause)

                        with m.If(arch_trap):
                            # Register RISC-V architectural trap in CSRs
                            m_csr.mcause.write(m, cause_entry)
                            m_csr.mepc.write(m, cause_register.pc)
                            self.trap_entry(m)

                        # Fetch is already stalled by ExceptionCauseRegister
                        with m.If(core_empty):
                            m.next = "TRAP_RESUME"
                        with m.Else():
                            m.next = "TRAP_FLUSH"

                    with m.Else():
                        # Normally retire all non-trap instructions
                        m.d.av_comb += commit.eq(1)

                    # TODO pass commit signal
                    self.ftq_commit(m, fb_instr_idx=rob_entry.rob_data.fb_instr_idx, exception=rob_entry.exception)

                    # Condition is used to avoid FRAT locking during normal operation
                    with condition(m) as cond:
                        with cond(commit):
                            retire_instr(rob_entry)
                        with cond():
                            # Not using default condition, because we want to block if branch is not ready
                            flush_instr(rob_entry)

                            m.d.comb += core_flushing.eq(1)

                    validate_transaction.schedule_before(retire_transaction)

            with m.State("TRAP_FLUSH"):
                with Transaction().body(m):
                    # Flush entire core
                    rob_entry = self.rob_peek(m)
                    self.rob_retire(m)

                    core_empty = self.instr_decrement(m)

                    flush_instr(rob_entry)

                    with m.If(core_empty):
                        m.next = "TRAP_RESUME"

                m.d.comb += core_flushing.eq(1)

            with m.State("TRAP_RESUME"):
                with Transaction().body(m):
                    # Resume core operation
                    self.perf_trap_latency.stop(m)

                    handler_pc = Signal(self.gen_params.isa.xlen)
                    # mtvec without mode is [mxlen-1:2], mode is two last bits. Only direct mode is supported
                    m.d.av_comb += handler_pc.eq(m_csr.mtvec.read(m).data & ~(0b11))

                    resume_pc = Mux(continue_pc_override, continue_pc, handler_pc)
                    m.d.sync += continue_pc_override.eq(0)

                    self.fetch_continue(m, pc=resume_pc, from_exception=1)

                    # Release pending trap state - allow accepting new reports
                    self.exception_cause_clear(m)

                    m.next = "NORMAL"

        # Disable executing any side effects from instructions in core when it is flushed
        m.d.comb += side_fx.eq(~fsm.ongoing("TRAP_FLUSH"))

        @def_method(m, self.core_state)
        def _():
            return {"flushing": core_flushing}

        @def_method(m, self.precommit)
        def _():
            rob_entry = self.rob_peek(m)
            return {"rob_id": rob_entry.rob_id, "side_fx": side_fx}

        return m
