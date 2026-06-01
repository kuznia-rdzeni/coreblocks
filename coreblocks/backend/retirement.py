from amaranth import *
from amaranth.lib.data import View
from transactron.utils import count_trailing_zeros, or_value
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

from transactron.core import Method, Methods, Transaction, TModule, def_method
from transactron.utils.dependencies import DependencyContext
from transactron.lib.metrics import *

from coreblocks.params.genparams import GenParams
from coreblocks.arch import ExceptionCause, PrivilegeLevel
from coreblocks.arch.csr_address import CounterEnableFieldOffsets
from coreblocks.interface.keys import (
    CoreStateKey,
    CSRInstancesKey,
    InstructionPrecommitKey,
)
from coreblocks.priv.csr.csr_instances import CSRAddress, counteren_access_filter
from coreblocks.priv.csr.csr_register import CSRRegister
from coreblocks.priv.csr.double_shadow import DoubleShadowCSR
from coreblocks.arch.isa_consts import TrapVectorMode


__all__ = ["Retirement"]


class Retirement(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
    ):
        self.gen_params = gen_params
        self.rob_peek = Method(o=gen_params.get(ROBLayouts).peek_layout)
        self.rob_retire = Method(i=gen_params.get(ROBLayouts).retire_layout)
        self.r_rat_commit = Methods(
            gen_params.retirement_superscalarity,
            i=gen_params.get(RATLayouts).rrat_commit_in,
            o=gen_params.get(RATLayouts).rrat_commit_out,
        )
        self.r_rat_peek = Methods(
            gen_params.retirement_superscalarity,
            i=gen_params.get(RATLayouts).rrat_peek_in,
            o=gen_params.get(RATLayouts).rrat_peek_out,
        )
        self.free_rf_put = Methods(gen_params.retirement_superscalarity, i=[("ident", range(gen_params.phys_regs))])
        self.rf_free = Methods(gen_params.retirement_superscalarity, i=gen_params.get(RFLayouts).rf_free)
        self.exception_cause_get = Method(o=gen_params.get(ExceptionRegisterLayouts).get)
        self.exception_cause_clear = Method()
        self.c_rat_restore = Methods(
            gen_params.retirement_superscalarity, i=gen_params.get(RATLayouts).crat_flush_restore
        )
        self.fetch_continue = Method(i=self.gen_params.get(FetchLayouts).resume)
        self.instr_decrement = Method(
            i=gen_params.get(CoreInstructionCounterLayouts).decrement_in,
            o=gen_params.get(CoreInstructionCounterLayouts).decrement_out,
        )
        self.trap_entry = Method(i=[("cause", gen_params.isa.xlen)], o=[("target_priv", PrivilegeLevel)])
        interrupt_controller_layouts = gen_params.get(InternalInterruptControllerLayouts)
        self.async_interrupt_cause = Method(o=interrupt_controller_layouts.interrupt_cause)
        self.checkpoint_tag_free = Method()
        self.checkpoint_get_active_tags = Method(o=gen_params.get(RATLayouts).get_active_tags_out)

        self._done_count = Signal(range(gen_params.retirement_superscalarity + 1))
        self.instret_csr = CSRRegister(None, gen_params, width=64, fu_read_map=lambda _, v: v + self._done_count)
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

        self.precommit = Method(i=layouts.precommit_in)
        self.dependency_manager.add_dependency(InstructionPrecommitKey(), self.precommit)

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr_ret, self.perf_trap_latency]

        csr_instances = self.dependency_manager.get_dependency(CSRInstancesKey())
        m_csr = csr_instances.m_mode
        s_csr = csr_instances.s_mode if self.gen_params.supervisor_mode else None
        m.submodules.instret_csr = self.instret_csr
        m.submodules.instret_shadow = self.instret_shadow

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

            self.perf_instr_ret.incr[i](m)

        def flush_instr(i: int, rob_entry: View):
            # get original rp_dst mapped to instruction rl_dst in R-RAT
            rat_out = self.r_rat_peek[i](m, rl_dst=rob_entry.rob_data.rl_dst)

            # free the "new" instruction rp_dst - result is flushed
            free_phys_reg(i, rob_entry.rob_data.rp_dst)

            # restore original rl_dst->rp_dst mapping in F-RAT
            self.c_rat_restore[i](m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rat_out.old_rp_dst)

        retire_valid = Signal()
        exception = Signal()
        continue_pc_override = Signal()
        continue_pc = Signal(self.gen_params.isa.xlen)
        core_flushing = Signal()
        trap_target_priv = Signal(PrivilegeLevel, init=PrivilegeLevel.MACHINE)

        retire_count = Signal(range(self.gen_params.retirement_superscalarity + 1))
        no_trap_count = Signal(range(self.gen_params.retirement_superscalarity + 1))
        tag_incr_mask = Signal(self.gen_params.retirement_superscalarity)
        safe_mask = Signal.like(tag_incr_mask)
        free_checkpoint = Signal()

        with Transaction().body(m):
            rob_entries = self.rob_peek(m)

            # CRAT can currently deallocate at most one tag per cycle, this logic reduces the retire rate
            # TODO: improve
            m.d.av_comb += tag_incr_mask.eq(Cat(entry.rob_data.tag_increment for entry in rob_entries.entries))
            m.d.av_comb += safe_mask.eq(tag_incr_mask & (tag_incr_mask - 1) | (-1 << rob_entries.done_count))
            m.d.av_comb += retire_count.eq(count_trailing_zeros(safe_mask))
            m.d.av_comb += free_checkpoint.eq(
                safe_mask != (tag_incr_mask | (-1 << rob_entries.done_count))[: len(safe_mask)]
            )

            exception_bits = Signal(self.gen_params.retirement_superscalarity)
            m.d.av_comb += exception_bits.eq(Cat(rob_entry.exception for rob_entry in rob_entries.entries))
            m.d.av_comb += no_trap_count.eq(count_trailing_zeros(exception_bits | safe_mask))
            m.d.av_comb += exception.eq(no_trap_count != retire_count)

            # Ensure that when exception is processed, correct entry is alredy in ExceptionCauseRegister
            ecr_entry = self.exception_cause_get(m)
            exception_one_hot = Signal.like(exception_bits)
            m.d.av_comb += exception_one_hot.eq(exception_bits & (~exception_bits + 1))
            exception_rob_id = or_value(
                Mux(exception_one_hot[i], rob_entry.rob_id, 0) for i, rob_entry in enumerate(rob_entries.entries)
            )
            m.d.av_comb += retire_valid.eq(Mux(exception, ecr_entry.valid & (ecr_entry.rob_id == exception_rob_id), 1))

        with m.FSM("NORMAL") as fsm:
            with m.State("NORMAL"):
                with Transaction(name="Retirement_NORMAL").body(m, ready=retire_valid):
                    self.rob_retire(m, count=retire_count)

                    with m.If(free_checkpoint):
                        self.checkpoint_tag_free(m)

                    core_empty = self.instr_decrement(m, count=retire_count)

                    commit_trapping = Signal()

                    with m.If(exception):
                        self.perf_trap_latency.start(m)

                        cause_register = self.exception_cause_get(m)

                        cause_entry = Signal(self.gen_params.isa.xlen)

                        arch_trap = Signal(init=1)

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
                        with m.Elif(cause_register.cause == ExceptionCause._COREBLOCKS_MISPREDICTION):
                            # Branch misprediction - commit jump, flush core and continue from correct pc.
                            m.d.av_comb += commit_trapping.eq(1)
                            # Do not modify trap related CSRs
                            m.d.av_comb += arch_trap.eq(0)

                            m.d.sync += continue_pc_override.eq(1)
                            m.d.sync += continue_pc.eq(cause_register.pc)
                        with m.Else():
                            # RISC-V synchronous exceptions - don't retire instruction that caused exception,
                            # and later resume from it.
                            # Value of ExceptionCauseRegister pc field is the instruction address.
                            m.d.av_comb += commit_trapping.eq(0)

                            m.d.av_comb += cause_entry.eq(cause_register.cause)

                        with m.If(arch_trap):
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
                        + Mux(exception, no_trap_count + commit_trapping, retire_count),
                    )

                    for i in range(self.gen_params.retirement_superscalarity):
                        with m.If(i - commit_trapping < no_trap_count):
                            retire_instr(i, rob_entries.entries[i])
                        with m.Elif(i < retire_count):
                            flush_instr(i, rob_entries.entries[i])

            with m.State("TRAP_FLUSH"):
                with Transaction(name="Retirement_FLUSH").body(m):
                    # Flush entire core
                    self.rob_retire(m, count=retire_count)

                    with m.If(free_checkpoint):
                        self.checkpoint_tag_free(m)

                    core_empty = self.instr_decrement(m, count=retire_count)

                    for i in range(self.gen_params.retirement_superscalarity):
                        with m.If(i < retire_count):
                            flush_instr(i, rob_entries.entries[i])

                    with m.If(core_empty):
                        m.next = "TRAP_RESUME"

            with m.State("TRAP_RESUME"):
                with Transaction(name="Retirement_RESUME").body(m):
                    # Resume core operation
                    self.perf_trap_latency.stop(m)

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

                    resume_pc = Mux(continue_pc_override, continue_pc, handler_pc)
                    m.d.sync += continue_pc_override.eq(0)

                    self.fetch_continue(m, pc=resume_pc)

                    # Release pending trap state - allow accepting new reports
                    self.exception_cause_clear(m)

                    m.next = "NORMAL"

        @def_method(m, self.core_state, nonexclusive=True)
        def _():
            return {"flushing": core_flushing}

        # Run precommit on first not-done instr, if exception not encountered
        precommit_rob_id = Signal(self.gen_params.rob_entries_bits)
        exc_prefixes = Array(
            [
                Cat(rob_entries.entries[j].exception for j in range(i)).any()
                for i in range(self.gen_params.retirement_superscalarity + 1)
            ]
        )
        m.d.comb += precommit_rob_id.eq(rob_entries.entries[0].rob_id + rob_entries.done_count)
        m.d.comb += self._done_count.eq(rob_entries.done_count)

        # Disable executing any side effects from instructions in core when it is flushed
        m.d.comb += core_flushing.eq(fsm.ongoing("TRAP_FLUSH") | exc_prefixes[rob_entries.done_count])

        # The argument is only used in argument validation, it is not needed in the method body.
        # A dummy combiner is provided.
        @def_method(
            m,
            self.precommit,
            ready=~core_flushing,
            validate_arguments=lambda rob_id: rob_id == precommit_rob_id,
            nonexclusive=True,
            combiner=lambda m, args, runs: 0,
        )
        def _(rob_id):
            return

        return m
