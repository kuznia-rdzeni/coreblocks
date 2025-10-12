from amaranth import *
from amaranth.lib.data import View
from coreblocks.interface.layouts import (
    CoreInstructionCounterLayouts,
    ExceptionRegisterLayouts,
    FetchLayouts,
    InternalInterruptControllerLayouts,
    RATLayouts,
    RFLayouts,
    ROBLayouts,
    RetirementLayouts,
)

from transactron.core import Method, Transaction, TModule, def_method
from transactron.lib.simultaneous import condition
from transactron.utils.dependencies import DependencyContext
from transactron.lib.metrics import *

from coreblocks.params.genparams import GenParams
from coreblocks.arch import ExceptionCause
from coreblocks.interface.keys import CoreStateKey, CSRInstancesKey, InstructionPrecommitKey
from coreblocks.priv.csr.csr_instances import CSRAddress, DoubleCounterCSR
from coreblocks.arch.isa_consts import TrapVectorMode


class Retirement(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        rrat_entries: View,
    ):
        self.gen_params = gen_params
        self.rrat_entries = rrat_entries

        self.rob_peek = Method(o=gen_params.get(ROBLayouts).peek_layout)
        self.rob_retire = Method()
        self.r_rat_commit = Method(
            i=gen_params.get(RATLayouts).rrat_commit_in, o=gen_params.get(RATLayouts).rrat_commit_out
        )
        self.free_rf_put = Method(i=[("ident", range(gen_params.phys_regs))])
        self.rf_free = Method(i=gen_params.get(RFLayouts).rf_free)
        self.exception_cause_get = Method(o=gen_params.get(ExceptionRegisterLayouts).get)
        self.exception_cause_clear = Method()
        self.c_rat_restore = Method(i=gen_params.get(RATLayouts).crat_flush_restore)
        self.fetch_resume_from_core_flush = Method(i=self.gen_params.get(FetchLayouts).resume)
        self.instr_decrement = Method(o=gen_params.get(CoreInstructionCounterLayouts).decrement)
        self.trap_entry = Method()
        self.async_interrupt_cause = Method(o=gen_params.get(InternalInterruptControllerLayouts).interrupt_cause)
        self.checkpoint_tag_free = Method()
        self.checkpoint_get_active_tags = Method(o=gen_params.get(RATLayouts).get_active_tags_out)

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)
        self.perf_instr_ret = HwCounter("backend.retirement.retired_instr", "Number of retired instructions")
        self.perf_trap_latency = FIFOLatencyMeasurer(
            "backend.retirement.trap_latency",
            "Cycles spent flushing the core after a trap",
            slots_number=1,
            max_latency=2 * 2**gen_params.rob_entries_bits,
        )

        self.layouts = self.gen_params.get(RetirementLayouts)
        self.dependency_manager = DependencyContext.get()
        self.core_state = Method(o=self.gen_params.get(RetirementLayouts).core_state)
        self.dependency_manager.add_dependency(CoreStateKey(), self.core_state)

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr_ret, self.perf_trap_latency]

        m_csr = self.dependency_manager.get_dependency(CSRInstancesKey()).m_mode
        m.submodules.instret_csr = self.instret_csr

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
            # we will copy full R-RAT mapping to C-RAT (F-RAT) in single cycle after last instruction is flushed
            # FUTURE-TODO: restore in single cycle with bitmask from RAT
            free_phys_reg(rob_entry.rob_data.rp_dst)

        def retire_inactive_instr(rob_entry):
            # F-RAT entry was already rolled back
            # free the "new" instruction rp_dst - result is flushed
            free_phys_reg(rob_entry.rob_data.rp_dst)

        retirement_last_tag = Signal(self.gen_params.tag_bits)

        retire_valid = Signal()
        instr_active = Signal()
        with Transaction().body(m) as validate_transaction:
            # Ensure that when exception is processed, correct entry is alredy in ExceptionCauseRegister
            rob_entry = self.rob_peek(m)
            ecr_entry = self.exception_cause_get(m)

            instr_tag = retirement_last_tag + rob_entry.rob_data.tag_increment

            m.d.comb += instr_active.eq(self.checkpoint_get_active_tags(m).active_tags[instr_tag])
            m.d.comb += retire_valid.eq(
                ~instr_active
                | (
                    ~rob_entry.exception
                    | (rob_entry.exception & ecr_entry.valid & (ecr_entry.rob_id == rob_entry.rob_id))
                )
            )

        core_flushing = Signal()

        with m.FSM("NORMAL") as fsm:
            with m.State("NORMAL"):
                with Transaction().body(m, request=retire_valid) as retire_transaction:
                    rob_entry = self.rob_peek(m)
                    self.rob_retire(m)

                    with m.If(rob_entry.rob_data.tag_increment):
                        m.d.sync += retirement_last_tag.eq(retirement_last_tag + 1)
                        self.checkpoint_tag_free(m)

                    core_empty = self.instr_decrement(m)

                    commit = Signal()

                    with m.If(rob_entry.exception & instr_active):
                        self.perf_trap_latency.start(m)

                        cause_register = self.exception_cause_get(m)

                        cause_entry = Signal(self.gen_params.isa.xlen)

                        arch_trap = Signal(init=1)

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
                            m_csr.mtval.write(m, cause_register.mtval)
                            self.trap_entry(m)

                        # Fetch is already stalled by ExceptionCauseRegister
                        with m.If(core_empty):
                            m.next = "TRAP_RESUME"
                        with m.Else():
                            m.next = "TRAP_FLUSH"

                    with m.Else():
                        # Retire non-trap instructions
                        m.d.av_comb += commit.eq(1)

                    # Condition is used to avoid FRAT locking during non-flush operation
                    with condition(m) as cond:
                        with cond(commit):
                            with m.If(instr_active):
                                retire_instr(rob_entry)
                            with m.Else():
                                retire_inactive_instr(rob_entry)
                        with cond():  # (Blocking if branch is not ready) , will not trigger on inactive instructions
                            flush_instr(rob_entry)

                            m.d.comb += core_flushing.eq(1)

                    validate_transaction.schedule_before(retire_transaction)

            with m.State("TRAP_FLUSH"):
                with Transaction().body(m):
                    # Flush entire core
                    rob_entry = self.rob_peek(m)
                    self.rob_retire(m)

                    with m.If(rob_entry.rob_data.tag_increment):
                        self.checkpoint_tag_free(m)

                    core_empty = self.instr_decrement(m)

                    flush_instr(rob_entry)

                    with m.If(core_empty):
                        m.next = "TRAP_RESUME"

                m.d.comb += core_flushing.eq(1)

            with m.State("TRAP_RESUME"):
                with Transaction().body(m):
                    # NOTE: FRAT state was previously restored instruction-by-instruction before introduction
                    # of checkpointing. Restoring RRAT -> [FRAT (inside CRAT)] in a single cycle on a core flush
                    # is simpler in hardware and as a concept :), but increases routing congestions.
                    # We may want to look into synthesis trade-offs later. See commit diff for changes in RRAT
                    # and restore logic.
                    self.c_rat_restore(m, entries=self.rrat_entries)

                    handler_pc = Signal(self.gen_params.isa.xlen)
                    mtvec_offset = Signal(self.gen_params.isa.xlen)
                    mtvec_base = m_csr.mtvec_base.read(m).data
                    mtvec_mode = m_csr.mtvec_mode.read(m).data
                    mcause = m_csr.mcause.read(m).data

                    # When mode is Vectored, interrupts set pc to base + 4 * cause_number
                    with m.If(mcause[-1] & (mtvec_mode == TrapVectorMode.VECTORED)):
                        m.d.av_comb += mtvec_offset.eq(mcause << 2)

                    # (mtvec_base stores base[MXLEN-1:2])
                    m.d.av_comb += handler_pc.eq((mtvec_base << 2) + mtvec_offset)
                    self.fetch_resume_from_core_flush(m, pc=handler_pc)

                    # Release pending trap state and the fetch lock
                    self.exception_cause_clear(m)

                    self.perf_trap_latency.stop(m)

                    m.next = "NORMAL"

        @def_method(m, self.core_state, nonexclusive=True)
        def _():
            return {"flushing": core_flushing}

        _precommit = Method(i=self.layouts.internal_precommit_in)

        # NOTE: Alternatively this could be done automagically bt returning new method on new key get
        def precommit(m: TModule, *, rob_id: Value, tag: Value):
            # Disable executing any side effects when core is flushing or instruction was
            # on a final wrong speculation path.

            side_fx = Signal()
            instr_active = self.checkpoint_get_active_tags(m).active_tags[tag]
            m.d.av_comb += side_fx.eq(~fsm.ongoing("TRAP_FLUSH") & instr_active)

            # separate function is used to avoid post-combiner speculation loop on argument dependent part
            # Call internal method to block until rob_id is on precommit position
            _precommit(m, rob_id=rob_id)

            ret = Signal(self.layouts.precommit_out)
            m.d.av_comb += ret.side_fx.eq(side_fx)
            return ret

        self.dependency_manager.add_dependency(InstructionPrecommitKey(), precommit)

        # The `rob_id` argument is only used in argument validation, it is not needed in the method body.
        # A dummy combiner is provided.
        rob_peek_id_val = Signal(self.gen_params.rob_entries_bits)

        @def_method(
            m,
            _precommit,
            validate_arguments=lambda rob_id: rob_id == rob_peek_id_val,
            nonexclusive=True,
            combiner=lambda m, args, runs: 0,
        )
        def _(rob_id):
            m.d.top_comb += rob_peek_id_val.eq(self.rob_peek(m).rob_id)

        return m
