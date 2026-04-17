from dataclasses import dataclass, KW_ONLY, field
from amaranth import *

from enum import IntFlag, auto, unique
from typing import Sequence
from coreblocks.arch.isa_consts import Funct12, Funct3, Funct7, Opcode, PrivilegeLevel, SatpMode


from transactron import *
from transactron.lib import logging
from transactron.lib.metrics import TaggedCounter
from transactron.lib.simultaneous import condition
from transactron.utils import DependencyContext, OneHotSwitch

from coreblocks.params import *
from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, ExceptionCause
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.interface.keys import (
    MretKey,
    SretKey,
    AsyncInterruptInsertSignalKey,
    ExceptionReportKey,
    CSRInstancesKey,
    InstructionPrecommitKey,
    UnsafeInstructionResolvedKey,
    FlushICacheKey,
    WaitForInterruptResumeKey,
)
from coreblocks.func_blocks.interface.func_protocols import FuncUnit

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager

log = logging.HardwareLogger("backend.fu.priv")


class PrivilegedFn(DecoderManager):
    def __init__(self, supervisor_enable=False) -> None:
        self.supervisor_enable = supervisor_enable

    @unique
    class Fn(IntFlag):
        MRET = auto()
        FENCEI = auto()
        WFI = auto()
        SRET = auto()
        SFENCEVMA = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.MRET, OpType.MRET),
            (self.Fn.FENCEI, OpType.FENCEI),
            (self.Fn.WFI, OpType.WFI),
        ] + [
            (self.Fn.SRET, OpType.SRET),
            (self.Fn.SFENCEVMA, OpType.SFENCEVMA),
        ] * self.supervisor_enable


class PrivilegedFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, priv_fn=PrivilegedFn()):
        self.gen_params = gen_params
        self.priv_fn = priv_fn

        self.layouts = layouts = gen_params.get(FuncUnitLayouts)
        self.dm = DependencyContext.get()

        self.issue = Method(i=layouts.issue)
        self.push_result = Method(i=layouts.push_result)

        self.perf_instr = TaggedCounter(
            "backend.fu.priv.instr",
            "Number of instructions precommited with side effects by the privilege unit",
            tags=PrivilegedFn.Fn,
        )

        self.exception_report = self.dm.get_dependency(ExceptionReportKey())()

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr]

        m.submodules.decoder = decoder = self.priv_fn.get_decoder(self.gen_params)

        instr_valid = Signal()
        finished = Signal()
        illegal_instruction = Signal()

        instr_rob = Signal(self.gen_params.rob_entries_bits)
        instr_pc = Signal(self.gen_params.isa.xlen)
        instr_fn = self.priv_fn.get_function()

        instr_imm = Signal(self.gen_params.isa.xlen)
        instr_s1_val = Signal(self.gen_params.isa.xlen)
        instr_s2_val = Signal(self.gen_params.isa.xlen)

        mret = self.dm.get_dependency(MretKey())
        sret = self.dm.get_optional_dependency(SretKey())
        async_interrupt_active = self.dm.get_dependency(AsyncInterruptInsertSignalKey())
        wfi_resume = self.dm.get_dependency(WaitForInterruptResumeKey())
        csr = self.dm.get_dependency(CSRInstancesKey())
        priv_mode = csr.m_mode.priv_mode
        flush_icache = self.dm.get_dependency(FlushICacheKey())
        resume_core = self.dm.get_dependency(UnsafeInstructionResolvedKey())

        @def_method(m, self.issue, ready=~instr_valid)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.sync += [
                instr_valid.eq(1),
                instr_rob.eq(arg.rob_id),
                instr_pc.eq(arg.pc),
                instr_fn.eq(decoder.decode_fn),
                instr_s1_val.eq(arg.s1_val),
                instr_s2_val.eq(arg.s2_val),
                instr_imm.eq(arg.imm),
            ]

        with Transaction().body(m, ready=instr_valid & ~finished):
            precommit = self.dm.get_dependency(InstructionPrecommitKey())
            info = precommit(m, instr_rob)
            m.d.sync += finished.eq(1)
            self.perf_instr.incr(m, instr_fn, enable_call=info.side_fx)

            priv_data = priv_mode.read(m).data

            illegal_mret = (instr_fn == PrivilegedFn.Fn.MRET) & (priv_data != PrivilegeLevel.MACHINE)

            if self.priv_fn.supervisor_enable:
                illegal_sret = (instr_fn == PrivilegedFn.Fn.SRET) & (
                    (priv_data == PrivilegeLevel.USER)
                    | ((priv_data == PrivilegeLevel.SUPERVISOR) & csr.m_mode.mstatus_tsr.read(m).data)
                )
            else:
                illegal_sret = 0

            if self.priv_fn.supervisor_enable:
                illegal_sfencevma = (instr_fn == PrivilegedFn.Fn.SFENCEVMA) & (
                    (priv_data == PrivilegeLevel.USER)
                    | ((priv_data == PrivilegeLevel.SUPERVISOR) & csr.m_mode.mstatus_tvm.read(m).data)
                )
            else:
                illegal_sfencevma = 0

            illegal_wfi = (instr_fn == PrivilegedFn.Fn.WFI) & (
                ((priv_data == PrivilegeLevel.USER) if self.gen_params.supervisor_mode else 0)
                | ((priv_data < PrivilegeLevel.MACHINE) & (csr.m_mode.mstatus_tw.read(m).data))
            )

            with condition(m, nonblocking=True) as branch:
                with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.MRET) & ~illegal_mret):
                    mret(m)
                if self.priv_fn.supervisor_enable:
                    assert sret is not None
                    with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.SRET) & ~illegal_sret):
                        sret(m)

                    # TODO: implement proper SFENCE.VMA, for BARE only - NO-OP is ok
                    assert self.gen_params.vmem_params.supported_schemes == {SatpMode.BARE}

                with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.FENCEI)):
                    flush_icache(m)
                with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.WFI) & ~illegal_wfi):
                    # async_interrupt_active implies wfi_resume. WFI should continue normal execution
                    # when interrupt is enabled in xie, but disabled via global mstatus.xIE
                    m.d.sync += finished.eq(wfi_resume)

            m.d.sync += illegal_instruction.eq(illegal_wfi | illegal_mret | illegal_sret | illegal_sfencevma)

        with Transaction().body(m, ready=instr_valid & finished):
            m.d.sync += instr_valid.eq(0)
            m.d.sync += finished.eq(0)

            ret_pc = Signal(self.gen_params.isa.xlen)

            with OneHotSwitch(m, instr_fn) as OneHotCase:
                with OneHotCase(PrivilegedFn.Fn.MRET):
                    m.d.av_comb += ret_pc.eq(csr.m_mode.mepc.read(m).data)
                if self.priv_fn.supervisor_enable:
                    with OneHotCase(PrivilegedFn.Fn.SRET):
                        m.d.av_comb += ret_pc.eq(csr.s_mode.sepc.read(m).data)
                # SFENCE.VMA, FENCE.I and WFI can't be compressed, so next PC is always pc+4
                if self.priv_fn.supervisor_enable:
                    with OneHotCase(PrivilegedFn.Fn.SFENCEVMA):
                        m.d.av_comb += ret_pc.eq(instr_pc + 4)
                with OneHotCase(PrivilegedFn.Fn.FENCEI):
                    m.d.av_comb += ret_pc.eq(instr_pc + 4)
                with OneHotCase(PrivilegedFn.Fn.WFI):
                    m.d.av_comb += ret_pc.eq(instr_pc + 4)

            with m.If(illegal_instruction):
                m.d.av_comb += ret_pc.eq(instr_pc)

            exception = Signal()
            with m.If(illegal_instruction):
                m.d.av_comb += exception.eq(1)

                # Replace with const zero if turns out not worth to re-encode instruction
                instr = Signal(self.gen_params.isa.xlen)
                m.d.av_comb += instr[0:2].eq(0b11)
                m.d.av_comb += instr[2:7].eq(Opcode.SYSTEM)
                m.d.av_comb += instr[7:12].eq(0)
                m.d.av_comb += instr[12:15].eq(Funct3.PRIV)
                m.d.av_comb += instr[15:20].eq(0)
                with m.Switch(instr_fn):
                    with m.Case(PrivilegedFn.Fn.MRET):
                        m.d.av_comb += instr[20:32].eq(Funct12.MRET)
                    with m.Case(PrivilegedFn.Fn.WFI):
                        m.d.av_comb += instr[20:32].eq(Funct12.WFI)
                    if self.priv_fn.supervisor_enable:
                        with m.Case(PrivilegedFn.Fn.SRET):
                            m.d.av_comb += instr[20:32].eq(Funct12.SRET)
                        with m.Case(PrivilegedFn.Fn.SFENCEVMA):
                            rs_size = self.gen_params.isa.reg_cnt_log
                            rs1_start = 32 - 2 * rs_size  # rs1 field
                            rs2_start = 32 - 3 * rs_size  # rs2 field
                            m.d.av_comb += instr[15:20].eq(instr_imm[rs1_start : rs1_start + rs_size])
                            m.d.av_comb += instr[20:25].eq(instr_imm[rs2_start : rs2_start + rs_size])
                            m.d.av_comb += instr[25:32].eq(Funct7.SFENCEVMA)
                    with m.Default():
                        m.d.av_comb += instr[20:32].eq(Funct12.MRET)
                        log.error(m, True, "missing Funct12 case")

                self.exception_report(
                    m, cause=ExceptionCause.ILLEGAL_INSTRUCTION, pc=ret_pc, rob_id=instr_rob, mtval=instr
                )
            with m.Elif(async_interrupt_active):
                # SPEC: "These conditions for an interrupt trap to occur [..] must also be evaluated immediately
                # following the execution of an xRET instruction."
                # mret() method is called from precommit() that was executed at least one cycle earlier (because
                # of finished condition). If calling mret() caused interrupt to be active, it is already represented
                # by updated async_interrupt_active signal.
                # Interrupt is reported on this xRET instruction with return address set to instruction that we
                # would normally return to (mepc value is preserved)
                m.d.av_comb += exception.eq(1)
                self.exception_report(
                    m, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=ret_pc, rob_id=instr_rob, mtval=0
                )
            with m.Else():
                log.info(m, True, "Unstalling fetch from the priv unit new_pc=0x{:x}", ret_pc)
                # Unstall the fetch
                resume_core(m, pc=ret_pc)

            self.push_result(
                m,
                rob_id=instr_rob,
                exception=exception,
                rp_dst=0,
                result=0,
            )

        return m


@dataclass(frozen=True)
class PrivilegedUnitComponent(FunctionalComponentParams):
    _: KW_ONLY
    supervisor_enable: bool = False
    decoder_manager: PrivilegedFn = field(init=False)

    def get_decoder_manager(self):
        return PrivilegedFn(supervisor_enable=self.supervisor_enable)

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return PrivilegedFuncUnit(gen_params, self.decoder_manager)
