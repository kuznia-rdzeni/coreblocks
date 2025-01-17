from dataclasses import dataclass
from amaranth import *

from enum import IntFlag, auto, unique
from typing import Sequence
from coreblocks.arch.isa_consts import Funct12, Funct3, Opcode, PrivilegeLevel


from transactron import *
from transactron.lib import BasicFifo, logging
from transactron.lib.metrics import TaggedCounter
from transactron.lib.simultaneous import condition
from transactron.utils import DependencyContext, OneHotSwitch

from coreblocks.params import *
from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, ExceptionCause
from coreblocks.interface.layouts import FuncUnitLayouts, FetchLayouts
from coreblocks.interface.keys import (
    MretKey,
    AsyncInterruptInsertSignalKey,
    ExceptionReportKey,
    CSRInstancesKey,
    InstructionPrecommitKey,
    FetchResumeKey,
    FlushICacheKey,
    WaitForInterruptResumeKey,
)
from coreblocks.func_blocks.interface.func_protocols import FuncUnit

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager


log = logging.HardwareLogger("backend.fu.priv")


class PrivilegedFn(DecoderManager):
    @unique
    class Fn(IntFlag):
        MRET = auto()
        FENCEI = auto()
        WFI = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [(cls.Fn.MRET, OpType.MRET), (cls.Fn.FENCEI, OpType.FENCEI), (cls.Fn.WFI, OpType.WFI)]


class PrivilegedFuncUnit(Elaboratable):
    def __init__(self, gen_params: GenParams, priv_fn=PrivilegedFn()):
        self.gen_params = gen_params
        self.priv_fn = priv_fn

        self.layouts = layouts = gen_params.get(FuncUnitLayouts)
        self.dm = DependencyContext.get()

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.fetch_resume_fifo = BasicFifo(self.gen_params.get(FetchLayouts).resume, 2)

        self.perf_instr = TaggedCounter(
            "backend.fu.priv.instr",
            "Number of instructions precommited with side effects by the priviledge unit",
            tags=PrivilegedFn.Fn,
        )

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

        mret = self.dm.get_dependency(MretKey())
        async_interrupt_active = self.dm.get_dependency(AsyncInterruptInsertSignalKey())
        wfi_resume = self.dm.get_dependency(WaitForInterruptResumeKey())
        exception_report = self.dm.get_dependency(ExceptionReportKey())
        csr = self.dm.get_dependency(CSRInstancesKey())
        priv_mode = csr.m_mode.priv_mode
        flush_icache = self.dm.get_dependency(FlushICacheKey())

        m.submodules.fetch_resume_fifo = self.fetch_resume_fifo

        @def_method(m, self.issue, ready=~instr_valid)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.sync += [
                instr_valid.eq(1),
                instr_rob.eq(arg.rob_id),
                instr_pc.eq(arg.pc),
                instr_fn.eq(decoder.decode_fn),
            ]

        with Transaction().body(m, request=instr_valid & ~finished):
            precommit = self.dm.get_dependency(InstructionPrecommitKey())
            info = precommit(m, instr_rob)
            m.d.sync += finished.eq(1)
            self.perf_instr.incr(m, instr_fn, cond=info.side_fx)

            priv_data = priv_mode.read(m).data

            illegal_mret = (instr_fn == PrivilegedFn.Fn.MRET) & (priv_data != PrivilegeLevel.MACHINE)
            # future todo: WFI should be illegal in U-Mode only if S-Mode is supported
            illegal_wfi = (
                (instr_fn == PrivilegedFn.Fn.WFI)
                & (priv_data == PrivilegeLevel.USER)
                & csr.m_mode.mstatus_tw.read(m).data
            )

            with condition(m, nonblocking=True) as branch:
                with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.MRET) & ~illegal_mret):
                    mret(m)
                with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.FENCEI)):
                    flush_icache(m)
                with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.WFI) & ~illegal_wfi):
                    # async_interrupt_active implies wfi_resume. WFI should continue normal execution
                    # when interrupt is enabled in xie, but disabled via global mstatus.xIE
                    m.d.sync += finished.eq(wfi_resume)

            m.d.sync += illegal_instruction.eq(illegal_wfi | illegal_mret)

        @def_method(m, self.accept, ready=instr_valid & finished)
        def _():
            m.d.sync += instr_valid.eq(0)
            m.d.sync += finished.eq(0)

            ret_pc = Signal(self.gen_params.isa.xlen)

            with OneHotSwitch(m, instr_fn) as OneHotCase:
                with OneHotCase(PrivilegedFn.Fn.MRET):
                    m.d.av_comb += ret_pc.eq(csr.m_mode.mepc.read(m).data)
                # FENCE.I and WFI can't be compressed, so the next instruction is always pc+4
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
                m.d.av_comb += instr[20:32].eq(Mux(instr_fn == PrivilegedFn.Fn.MRET, Funct12.WFI, Funct12.MRET))
                log.error(
                    m, (instr_fn != PrivilegedFn.Fn.MRET) & (instr_fn != PrivilegedFn.Fn.WFI), "missing Funct12 case"
                )

                exception_report(m, cause=ExceptionCause.ILLEGAL_INSTRUCTION, pc=ret_pc, rob_id=instr_rob, mtval=instr)
            with m.Elif(async_interrupt_active):
                # SPEC: "These conditions for an interrupt trap to occur [..] must also be evaluated immediately
                # following the execution of an xRET instruction."
                # mret() method is called from precommit() that was executed at least one cycle earlier (because
                # of finished condition). If calling mret() caused interrupt to be active, it is already represented
                # by updated async_interrupt_active signal.
                # Interrupt is reported on this xRET instruction with return address set to instruction that we
                # would normally return to (mepc value is preserved)
                m.d.av_comb += exception.eq(1)
                exception_report(
                    m, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=ret_pc, rob_id=instr_rob, mtval=0
                )
            with m.Else():
                log.info(m, True, "Unstalling fetch from the priv unit new_pc=0x{:x}", ret_pc)
                # Unstall the fetch
                self.fetch_resume_fifo.write(m, pc=ret_pc)

            return {
                "rob_id": instr_rob,
                "exception": exception,
                "rp_dst": 0,
                "result": 0,
            }

        return m


@dataclass(frozen=True)
class PrivilegedUnitComponent(FunctionalComponentParams):
    decoder_manager: PrivilegedFn = PrivilegedFn()

    def get_module(self, gp: GenParams) -> FuncUnit:
        unit = PrivilegedFuncUnit(gp, self.decoder_manager)
        connections = DependencyContext.get()
        connections.add_dependency(FetchResumeKey(), unit.fetch_resume_fifo.read)
        return unit
