from amaranth import *
from amaranth.lib.data import View
from coreblocks.interface.layouts import (
    CoreInstructionCounterLayouts,
    ExceptionInformationRegisterLayouts,
    FetchLayouts,
    InternalInterruptControllerLayouts,
    RATLayouts,
    RFLayouts,
    ROBLayouts,
    RetirementLayouts,
    FTQPtr,
)

from transactron.core import Method, Methods, Transaction, TModule, def_method
from transactron.evlog import EventSource
from transactron.utils import HardwareLogger, DependencyContext, count_trailing_zeros, OneHotMux, popcount
from transactron.lib.metrics import *

from coreblocks.telemetry import RobFlush, RobRetire

from coreblocks.params.genparams import GenParams
from coreblocks.arch import ExceptionCause, HPMEvent, PrivilegeLevel
from coreblocks.arch.csr_address import CounterEnableFieldOffsets
from coreblocks.interface.keys import (
    ActiveTagsKey,
    CoreStateKey,
    CSRInstancesKey,
    RVVIHartCollectorKey,
    SideFxGuardKey,
    FTQCommitKey,
)
from coreblocks.priv.csr.csr_instances import CSRAddress, counteren_access_filter
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.double_shadow import DoubleShadowCSR
from coreblocks.arch.isa_consts import TrapVectorMode


__all__ = ["Retirement"]


log = HardwareLogger("backend.retirement")
evlog = EventSource("backend.retirement")


class Retirement(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.rob_peek = Method(o=gen_params.get(ROBLayouts).peek_layout)
        self.rob_retire = Method(i=gen_params.get(ROBLayouts).retire_layout)
        self.r_rat_commit = Methods(
            gen_params.retirement_superscalarity,
            i=gen_params.get(RATLayouts).rrat_commit_in,
            o=gen_params.get(RATLayouts).rrat_commit_out,
        )
        self.r_rat_peek = Method(
            o=gen_params.get(RATLayouts).rrat_peek_out,
        )
        self.free_rf_put = Methods(gen_params.retirement_superscalarity, i=[("ident", range(gen_params.phys_regs))])
        self.rf_free = Methods(gen_params.retirement_superscalarity, i=gen_params.get(RFLayouts).rf_free)
        self.exception_cause_get = Method(o=gen_params.get(ExceptionInformationRegisterLayouts).get)
        self.exception_cause_clear = Method()
        self.c_rat_restore = Method(i=gen_params.get(RATLayouts).crat_flush_restore_in)
        self.fetch_redirect = Method(i=self.gen_params.get(FetchLayouts).backend_redirect)
        self.instr_decrement = Method(
            i=gen_params.get(CoreInstructionCounterLayouts).decrement_in,
            o=gen_params.get(CoreInstructionCounterLayouts).decrement_out,
        )
        self.trap_entry = Method(i=[("cause", gen_params.isa.xlen)], o=[("target_priv", PrivilegeLevel)])
        interrupt_controller_layouts = gen_params.get(InternalInterruptControllerLayouts)
        self.async_interrupt_cause = Method(o=interrupt_controller_layouts.interrupt_cause)
        self.checkpoint_tag_free = Method()

        self.pure_active_count = Signal(range(gen_params.retirement_superscalarity + 1))
        self.instret_csr = CSRRegister(None, gen_params, width=64, fu_read_map=lambda _, v: v + self.pure_active_count)
        self.instret_shadow = DoubleShadowCSR(
            gen_params,
            self.instret_csr,
            CSRAddress.MINSTRET,
            CSRAddress.MINSTRETH,
            CSRAddress.INSTRET,
            CSRAddress.INSTRETH,
            shadow_access_filter=counteren_access_filter(gen_params, CounterEnableFieldOffsets.IR),
        )
        self.perf_instr_ret = HwCounter(
            "backend.retirement.retired_instr",
            "Number of retired instructions",
            ways=gen_params.retirement_superscalarity,
        )
        self.perf_mispredictions = HwCounter(
            "backend.retirement.mispredictions", "Number of committed branch mispredictions"
        )
        self.perf_trap_latency = FIFOLatencyMeasurer(
            "backend.retirement.trap_latency",
            "Cycles spent flushing the core after a trap",
            slots_number=1,
            max_latency=2 * 2**gen_params.rob_entries_bits,
        )

        layouts = self.gen_params.get(RetirementLayouts)
        self.dependency_manager = DependencyContext.get()
        self.core_state = Method(o=self.gen_params.get(RetirementLayouts).core_state)
        self.dependency_manager.add_dependency(CoreStateKey(), self.core_state)

        self.side_fx_guard = Method(i=layouts.side_fx_guard_in)
        self.dependency_manager.add_dependency(SideFxGuardKey(), self.side_fx_guard)

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr_ret, self.perf_mispredictions, self.perf_trap_latency]

        csr_instances = self.dependency_manager.get_dependency(CSRInstancesKey())
        m_csr = csr_instances.m_mode
        s_csr = csr_instances.s_mode if self.gen_params.supervisor_mode else None
        m.submodules.instret_csr = self.instret_csr
        m.submodules.instret_shadow = self.instret_shadow

        rvvi = self.dependency_manager.get_optional_dependency(RVVIHartCollectorKey())

        ftq_commit = self.dependency_manager.get_dependency(FTQCommitKey())

        def free_phys_reg(i: int, rp_dst: Value):
            # mark reg in Register File as free
            self.rf_free[i](m, rp_dst)
            # put to Free RF list
            with m.If(rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put[i](m, rp_dst)

        def retire_instr(i: int, rob_entry: View):
            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit[i](m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst)

            # free old rp_dst from overwritten R-RAT mapping
            free_phys_reg(i, rat_out.old_rp_dst)

            evlog.emit(m, RobRetire.hw(rob_id=rob_entry.rob_id))

            self.perf_instr_ret.incr[i](m)

            log.info(
                m,
                not self.gen_params.has_rvvi,
                "Retired instruction #{}: rl_dst x{} rp_dst p{} rob_id 0x{:x}",
                i,
                rob_entry.rob_data.rl_dst,
                rob_entry.rob_data.rp_dst,
                rob_entry.rob_id,
            )

        def flush_instr(i: int, rob_entry: View):
            evlog.emit(m, RobFlush.hw(rob_id=rob_entry.rob_id))

            # free the "new" instruction rp_dst - result is discarded
            free_phys_reg(i, rob_entry.rob_data.rp_dst)

            log.debug(
                m,
                True,
                "Flushed instruction rob_id 0x{:x} freeing p{}",
                rob_entry.rob_id,
                rob_entry.rob_data.rp_dst,
            )

        retire_valid = Signal()
        exception = Signal()
        trap_target_priv = Signal(PrivilegeLevel, init=PrivilegeLevel.MACHINE)
        ftq_commit_ptr = FTQPtr(gen_params=self.gen_params)

        last_retired_tag = Signal(self.gen_params.tag_bits)
        next_last_retired_tag = Signal.like(last_retired_tag)

        retire_count = Signal(range(self.gen_params.retirement_superscalarity + 1))
        no_trap_count = Signal.like(retire_count)
        active_no_trap_count = Signal.like(retire_count)
        done_count = Signal.like(retire_count)
        tag_incr_mask = Signal(self.gen_params.retirement_superscalarity)
        retiring_mask = Signal.like(tag_incr_mask)
        tag_active_mask = Signal.like(tag_incr_mask)
        done_mask = Signal.like(tag_incr_mask)
        done_ignore_mask = Signal.like(tag_incr_mask)
        first_tag_incr_mask = Signal.like(tag_incr_mask)
        limiting_instruction_mask = Signal.like(tag_incr_mask)
        free_tag = Signal()
        last_retired_active = Signal()

        with Transaction().always_body(m):
            rob_entries = self.rob_peek(m)
            active_tags = self.dependency_manager.get_dependency(ActiveTagsKey())(m).active_tags
            ecr_entry = self.exception_cause_get(m)

        # CRAT can currently deallocate at most one tag per cycle, this logic reduces the retire rate
        # TODO: improve
        m.d.comb += tag_incr_mask.eq(Cat(entry.rob_data.tag_increment for entry in rob_entries.entries))
        m.d.comb += done_mask.eq(Cat(entry.done for entry in rob_entries.entries))
        m.d.comb += done_count.eq(count_trailing_zeros(~done_mask))
        m.d.comb += done_ignore_mask.eq(~done_mask | -(~done_mask))
        m.d.comb += limiting_instruction_mask.eq((tag_incr_mask & (tag_incr_mask - 1)) | done_ignore_mask)

        m.d.comb += retire_count.eq(count_trailing_zeros(limiting_instruction_mask))
        m.d.comb += retiring_mask.eq(~(limiting_instruction_mask | -limiting_instruction_mask))
        m.d.comb += free_tag.eq((tag_incr_mask & retiring_mask).any())

        m.d.comb += first_tag_incr_mask.eq(tag_incr_mask | done_ignore_mask)
        first_tag_incr_pos = count_trailing_zeros(first_tag_incr_mask)
        m.d.comb += next_last_retired_tag.eq(Mux(free_tag, last_retired_tag + 1, last_retired_tag))
        tag_active_mask_suffix = Mux(
            active_tags[last_retired_tag], ~(first_tag_incr_mask | -first_tag_incr_mask), 0
        )  # last retired tag until limiting incr (if exsists)
        tag_active_mask_prefix = (
            -active_tags[next_last_retired_tag] << first_tag_incr_pos
        )  # the same tag from limiting bit increase up
        m.d.comb += tag_active_mask.eq((tag_active_mask_suffix | tag_active_mask_prefix) & retiring_mask)

        exception_bits = Signal(self.gen_params.retirement_superscalarity)
        m.d.comb += exception_bits.eq(Cat(rob_entry.exception for rob_entry in rob_entries.entries) & tag_active_mask)
        m.d.comb += no_trap_count.eq(count_trailing_zeros(exception_bits | ~retiring_mask))
        m.d.comb += active_no_trap_count.eq(popcount(~(exception_bits | -exception_bits) & tag_active_mask))
        m.d.comb += exception.eq((exception_bits & retiring_mask).any())

        # Ensure that when exception is processed, correct entry is alredy in ExceptionCauseRegister
        exception_rob_id = OneHotMux.create(
            m,
            [
                (rob_entry.exception & tag_active_mask[i], rob_entry.rob_id)
                for i, rob_entry in enumerate(rob_entries.entries)
            ],
            priority=True,
        )
        m.d.comb += retire_valid.eq(Mux(exception, ecr_entry.valid & (ecr_entry.data.rob_id == exception_rob_id), 1))

        with m.FSM("NORMAL") as fsm:
            with m.State("NORMAL"):
                with Transaction(name="Retirement_NORMAL").body(m, ready=retire_valid):
                    self.rob_retire(m, count=retire_count)

                    with m.If(free_tag):
                        self.checkpoint_tag_free(m)
                        m.d.sync += last_retired_tag.eq(last_retired_tag + 1)

                    core_empty = self.instr_decrement(m, count=retire_count)

                    commit_trapping = Signal()

                    cause_register = self.exception_cause_get(m).data
                    arch_trap = Signal(init=1)

                    with m.If(exception):
                        self.perf_trap_latency.start(m)

                        cause_entry = Signal(self.gen_params.isa.xlen)

                        with m.If(cause_register.cause == ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT):
                            # Async interrupts are inserted only by JumpBranchUnit and conditionally by MRET and CSR
                            # The PC field is set to address of instruction to resume from interrupt (e.g. for jumps
                            # it is a jump result).
                            # Instruction that reported interrupt is the last one that is committed.
                            m.d.av_comb += commit_trapping.eq(1)

                            # Set MSB - the Interrupt bit
                            m.d.av_comb += cause_entry.eq(
                                (1 << (self.gen_params.isa.xlen - 1)) | self.async_interrupt_cause(m).cause
                            )
                        with m.Else():
                            # RISC-V synchronous exceptions - don't retire instruction that caused exception,
                            # and later resume from it.
                            # Value of ExceptionCauseRegister pc field is the instruction address.
                            m.d.av_comb += commit_trapping.eq(0)

                            m.d.av_comb += cause_entry.eq(cause_register.cause)

                        # Register RISC-V architectural trap in CSRs.
                        target_priv = self.trap_entry(m, cause=cause_entry).target_priv

                        def set_trap_csrs(cause_reg, epc_reg, tval_reg):
                            cause_reg.write(m, cause_entry)
                            epc_reg.write(m, cause_register.pc)
                            tval_reg.write(m, cause_register.mtval)

                        with m.Switch(target_priv):
                            if self.gen_params.supervisor_mode:
                                with m.Case(PrivilegeLevel.SUPERVISOR):
                                    assert s_csr is not None
                                    set_trap_csrs(s_csr.scause, s_csr.sepc, s_csr.stval)
                            with m.Case(PrivilegeLevel.MACHINE):
                                set_trap_csrs(m_csr.mcause, m_csr.mepc, m_csr.mtval)

                            m.d.sync += trap_target_priv.eq(target_priv)

                        # Fetch is already stalled by ExceptionCauseRegister
                        with m.If(core_empty):
                            m.next = "TRAP_RESUME"
                        with m.Else():
                            m.next = "TRAP_FLUSH"

                    self.instret_csr.write(
                        m,
                        data=self.instret_csr.read(m).data
                        + Mux(exception, active_no_trap_count + commit_trapping, popcount(tag_active_mask)),
                    )

                    last_commit_ftq_ptr = Signal.like(rob_entries.entries[0].rob_data.ftq_ptr)
                    last_commit_ftq_ptr_v = Signal()
                    for i in range(self.gen_params.retirement_superscalarity):
                        entry = rob_entries.entries[i]

                        with m.If(i - commit_trapping < no_trap_count):
                            with m.If(tag_active_mask[i]):
                                retire_instr(i, rob_entries.entries[i])

                                if rvvi is not None:
                                    rvvi.finalize_retire[i](
                                        m,
                                        rob_id=entry.rob_id,
                                        rl_dst=entry.rob_data.rl_dst,
                                        rp_dst=entry.rob_data.rp_dst,
                                        trap=entry.exception & arch_trap,
                                        interrupt=entry.exception
                                        & (cause_register.cause == ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT),
                                    )

                                m.d.av_comb += last_commit_ftq_ptr.eq(rob_entries.entries[i].rob_data.ftq_ptr)
                                m.d.av_comb += last_commit_ftq_ptr_v.eq(1)
                                m.d.sync += last_retired_active.eq(1)
                            with m.Else():
                                # flush inactive instruction - CRAT entry was already rolled back
                                flush_instr(i, rob_entries.entries[i])
                                m.d.sync += last_retired_active.eq(0)

                        with m.Elif(i < retire_count):
                            # hard flush instruction for trap handling
                            flush_instr(i, rob_entries.entries[i])

                    # TODO: this is some approximation of misprediction events - looking for active -> inactive
                    # changes in retired instructions.
                    # More metadata needs to be stored for an accurate result, improve.
                    active_mask_with_prev = Signal(tag_active_mask.shape().width + 1)
                    m.d.comb += active_mask_with_prev.eq(Cat(last_retired_active, tag_active_mask))
                    change_mask = active_mask_with_prev & ~tag_active_mask
                    with m.If((change_mask & retiring_mask).any()):  # without last bit
                        self.perf_mispredictions.incr(m)
                        m_csr.hpm_event_report(m, events=1 << HPMEvent.BRANCH_MISPREDICTION)

                    # Commit the FTQ entry for the last retired instruction this cycle.
                    with m.If(last_commit_ftq_ptr_v):
                        ftq_commit(m, ftq_ptr=last_commit_ftq_ptr)
                        m.d.sync += ftq_commit_ptr.eq(last_commit_ftq_ptr)

            with m.State("TRAP_FLUSH"):
                with Transaction(name="Retirement_FLUSH").body(m):
                    # Flush entire core
                    self.rob_retire(m, count=retire_count)

                    with m.If(free_tag):
                        self.checkpoint_tag_free(m)
                        m.d.sync += last_retired_tag.eq(last_retired_tag + 1)

                    core_empty = self.instr_decrement(m, count=retire_count)

                    for i in range(self.gen_params.retirement_superscalarity):
                        with m.If(i < retire_count):
                            flush_instr(i, rob_entries.entries[i])

                    with m.If(core_empty):
                        m.next = "TRAP_RESUME"

            with m.State("TRAP_RESUME"):
                with Transaction(name="Retirement_RESUME").body(m):
                    # Resume core operation
                    self.c_rat_restore(m, entries=self.r_rat_peek(m).entries)
                    self.perf_trap_latency.stop(m)
                    log.debug(m, True, "Resuming core from the retirement")

                    handler_pc = Signal(self.gen_params.isa.xlen)
                    tvec_offset = Signal(self.gen_params.isa.xlen)
                    tvec_base = Signal(self.gen_params.isa.xlen)
                    tvec_mode = Signal(TrapVectorMode)
                    tcause = Signal(self.gen_params.isa.xlen)

                    def set_vals(reg_base, reg_mode, reg_cause):
                        m.d.av_comb += [
                            tvec_base.eq(reg_base.read(m).data),
                            tvec_mode.eq(reg_mode.read(m).data),
                            tcause.eq(reg_cause.read(m).data),
                        ]

                    with m.Switch(trap_target_priv):
                        if self.gen_params.supervisor_mode:
                            with m.Case(PrivilegeLevel.SUPERVISOR):
                                assert s_csr is not None
                                set_vals(s_csr.stvec_base, s_csr.stvec_mode, s_csr.scause)
                        with m.Case(PrivilegeLevel.MACHINE):
                            set_vals(m_csr.mtvec_base, m_csr.mtvec_mode, m_csr.mcause)

                    # When mode is Vectored, interrupts set pc to base + 4 * cause_number
                    with m.If(tcause[-1] & (tvec_mode == TrapVectorMode.VECTORED)):
                        m.d.av_comb += tvec_offset.eq(tcause << 2)

                    # (xtvec_base stores base[MXLEN-1:2])
                    m.d.av_comb += handler_pc.eq((tvec_base << 2) + tvec_offset)

                    self.fetch_redirect(m, ftq_ptr=ftq_commit_ptr, pc=handler_pc)
                    m.d.sync += last_retired_active.eq(1)

                    # Release pending trap state - allow accepting new reports and unstall fetch
                    self.exception_cause_clear(m)

                    m.next = "NORMAL"

        @def_method(m, self.core_state, nonexclusive=True)
        def _():
            return {"flushing": fsm.ongoing("TRAP_FLUSH")}

        # Run side fx on first non-pure instr, if exception not encountered
        impure_mask = Signal(range(self.gen_params.retirement_superscalarity))
        pure_count = Signal(range(self.gen_params.retirement_superscalarity + 1))
        m.d.comb += impure_mask.eq(Cat(~entry.pure for entry in rob_entries.entries))
        m.d.comb += pure_count.eq(count_trailing_zeros(impure_mask))
        side_fx_rob_id = Signal(self.gen_params.rob_entries_bits)
        exc_prefixes = Array(
            [
                Cat(rob_entries.entries[j].exception for j in range(i)).any()
                for i in range(self.gen_params.retirement_superscalarity + 1)
            ]
        )
        m.d.comb += side_fx_rob_id.eq(rob_entries.entries[0].rob_id + pure_count)

        current_tag_expr = last_retired_tag
        pure_inactive_offset = Signal(self.gen_params.retirement_superscalarity)
        for i, entry in enumerate(rob_entries.entries):
            # FUTURE-TODO: unify with the other tag mask when we would support retiring multiple tags in single cycle
            current_tag_expr += entry.rob_data.tag_increment
            current_tag = Signal(self.gen_params.tag_bits)
            m.d.comb += current_tag.eq(current_tag_expr)
            m.d.comb += pure_inactive_offset[i].eq(~active_tags[current_tag] & (~(impure_mask | -impure_mask))[i])

        m.d.comb += self.pure_active_count.eq(pure_count - popcount(pure_inactive_offset))

        # Disable executing any side effects from instructions in core when it is flushed
        core_flushing = Signal()
        m.d.comb += core_flushing.eq(
            fsm.ongoing("TRAP_FLUSH") | exc_prefixes[done_count]
        )  # FIXME: this check is too restrictive but it will work

        # The argument is only used in argument validation, it is not needed in the method body. A dummy combiner is
        # provided.
        @def_method(
            m,
            self.side_fx_guard,
            ready=~core_flushing,
            validate_arguments=lambda rob_id, tag, require_done: (rob_id == side_fx_rob_id)
            & (~require_done | (pure_count == done_count))
            & active_tags[tag],  # FUTURE-TODO: inactive instructions are pure
            nonexclusive=True,
            combiner=lambda m, args, runs: {"rob_id": 0, "tag": 0, "require_done": 0},
        )
        def _(rob_id, tag, require_done):
            return

        return m
