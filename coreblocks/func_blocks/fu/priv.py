from amaranth import *

from enum import IntFlag, auto, unique
from typing import Sequence


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
    AsyncInterruptInsertSignalKey,
    ExceptionReportKey,
    GenericCSRRegistersKey,
    InstructionPrecommitKey,
    FetchResumeKey,
    FlushICacheKey,
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
    def __init__(self, gp: GenParams):
        self.gp = gp
        self.priv_fn = PrivilegedFn()

        self.layouts = layouts = gp.get(FuncUnitLayouts)
        self.dm = DependencyContext.get()

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.perf_instr = TaggedCounter(
            "backend.fu.priv.instr",
            "Number of instructions precommited with side effects by the priviledge unit",
            tags=PrivilegedFn.Fn,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr]

        m.submodules.decoder = decoder = self.priv_fn.get_decoder(self.gp)

        instr_valid = Signal()
        finished = Signal()

        instr_rob = Signal(self.gp.rob_entries_bits)
        instr_pc = Signal(self.gp.isa.xlen)
        instr_fn = self.priv_fn.get_function()

        mret = self.dm.get_dependency(MretKey())
        async_interrupt_active = self.dm.get_dependency(AsyncInterruptInsertSignalKey())
        exception_report = self.dm.get_dependency(ExceptionReportKey())
        csr = self.dm.get_dependency(GenericCSRRegistersKey())
        flush_icache = self.dm.get_dependency(FlushICacheKey())
        fetch_resume = self.dm.get_dependency(FetchResumeKey())

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
            info = precommit(m)
            with m.If(info.rob_id == instr_rob):
                m.d.sync += finished.eq(1)
                self.perf_instr.incr(m, instr_fn, cond=info.side_fx)

                with condition(m, nonblocking=True) as branch:
                    with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.MRET)):
                        mret(m)
                    with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.FENCEI)):
                        flush_icache(m)
                    with branch(info.side_fx & (instr_fn == PrivilegedFn.Fn.WFI)):
                        m.d.sync += finished.eq(async_interrupt_active)

        @def_method(m, self.accept, ready=instr_valid & finished)
        def _():
            m.d.sync += instr_valid.eq(0)
            m.d.sync += finished.eq(0)

            ret_pc = Signal(self.gp.isa.xlen)

            with OneHotSwitch(m, instr_fn) as OneHotCase:
                with OneHotCase(PrivilegedFn.Fn.MRET):
                    m.d.av_comb += ret_pc.eq(csr.m_mode.mepc.read(m).data)
                # FENCE.I and WFI can't be compressed, so the next instruction is always pc+4
                with OneHotCase(PrivilegedFn.Fn.FENCEI):
                    m.d.av_comb += ret_pc.eq(instr_pc + 4)
                with OneHotCase(PrivilegedFn.Fn.WFI):
                    m.d.av_comb += ret_pc.eq(instr_pc + 4)

            exception = Signal()
            with m.If(async_interrupt_active):
                # SPEC: "These conditions for an interrupt trap to occur [..] must also be evaluated immediately
                # following the execution of an xRET instruction."
                # mret() method is called from precommit() that was executed at least one cycle earlier (because
                # of finished condition). If calling mret() caused interrupt to be active, it is already represented
                # by updated async_interrupt_active singal.
                # Interrupt is reported on this xRET instruction with return address set to instruction that we
                # would normally return to (mepc value is preserved)
                m.d.comb += exception.eq(1)
                exception_report(m, cause=ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT, pc=ret_pc, rob_id=instr_rob)
            with m.Else():
                log.info(m, True, "Unstalling fetch from the priv unit new_pc=0x{:x}", ret_pc)
                # Unstall the fetch
                fetch_resume(m, pc=ret_pc, from_exception=0)

            return {
                "rob_id": instr_rob,
                "exception": exception,
                "rp_dst": 0,
                "result": 0,
            }

        return m


class PrivilegedUnitComponent(FunctionalComponentParams):
    def get_module(self, gp: GenParams) -> FuncUnit:
        return PrivilegedFuncUnit(gp)

    def get_optypes(self) -> set[OpType]:
        return PrivilegedFn().get_op_types()
