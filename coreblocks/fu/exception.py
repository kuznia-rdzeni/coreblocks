from typing import Sequence
from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.isa import Funct3, ExceptionCause
from coreblocks.params.layouts import FetchLayouts

from transactron import *
from transactron.lib import FIFO

from coreblocks.params import OpType, GenParams, FuncUnitLayouts, FunctionalComponentParams
from transactron.utils import OneHotSwitch
from coreblocks.params.keys import BranchResolvedKey, ExceptionReportKey, GenericCSRRegistersKey, MretKey

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.utils.protocols import FuncUnit

__all__ = ["ExceptionFuncUnit", "ExceptionUnitComponent"]


class ExceptionUnitFn(DecoderManager):
    class Fn(IntFlag):
        ECALL = auto()
        EBREAK = auto()
        MRET = auto()
        # Fns representing exceptions caused by instructions before FUs
        INSTR_ACCESS_FAULT = auto()
        ILLEGAL_INSTRUCTION = auto()
        BREAKPOINT = auto()
        INSTR_PAGE_FAULT = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.ECALL, OpType.ECALL),
            (self.Fn.EBREAK, OpType.EBREAK),
            (self.Fn.MRET, OpType.MRET),
            (self.Fn.INSTR_ACCESS_FAULT, OpType.EXCEPTION, Funct3._EINSTRACCESSFAULT),
            (self.Fn.ILLEGAL_INSTRUCTION, OpType.EXCEPTION, Funct3._EILLEGALINSTR),
            (self.Fn.BREAKPOINT, OpType.EXCEPTION, Funct3._EBREAKPOINT),
            (self.Fn.INSTR_PAGE_FAULT, OpType.EXCEPTION, Funct3._EINSTRPAGEFAULT),
        ]


class ExceptionFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, unit_fn=ExceptionUnitFn()):
        self.gen_params = gen_params
        self.fn = unit_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.dm = gen_params.get(DependencyManager)

        self.branch_verify_fifo = FIFO(self.gen_params.get(FetchLayouts).branch_verify, 2)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.branch_verify_fifo += self.branch_verify_fifo
        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)

        report = self.dm.get_dependency(ExceptionReportKey())
        mret = self.dm.get_dependency(MretKey())
        csr = self.dm.get_dependency(GenericCSRRegistersKey())

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            cause = Signal(ExceptionCause)
            exception = Signal()
            pc = Signal(self.gen_params.isa.xlen)

            m.d.comb += exception.eq(1)
            m.d.comb += pc.eq(arg.pc)

            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(ExceptionUnitFn.Fn.EBREAK):
                    m.d.comb += cause.eq(ExceptionCause.BREAKPOINT)
                with OneHotCase(ExceptionUnitFn.Fn.ECALL):
                    # TODO: Switch privilege level when implemented
                    m.d.comb += cause.eq(ExceptionCause.ENVIRONMENT_CALL_FROM_M)
                with OneHotCase(ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT):
                    m.d.comb += cause.eq(ExceptionCause.INSTRUCTION_ACCESS_FAULT)
                with OneHotCase(ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION):
                    m.d.comb += cause.eq(ExceptionCause.ILLEGAL_INSTRUCTION)
                with OneHotCase(ExceptionUnitFn.Fn.BREAKPOINT):
                    m.d.comb += cause.eq(ExceptionCause.BREAKPOINT)
                with OneHotCase(ExceptionUnitFn.Fn.INSTR_PAGE_FAULT):
                    m.d.comb += cause.eq(ExceptionCause.INSTRUCTION_PAGE_FAULT)
                with OneHotCase(ExceptionUnitFn.Fn.MRET):
                    next_interrupt = mret(m)
                    m.d.comb += exception.eq(next_interrupt)
                    m.d.comb += pc.eq(csr.m_mode.mepc.read(m))
                    with m.If(next_interrupt):
                        # Trigger interrupt if it would unblock after MRET immediately (required by SPEC)
                        # with return pc of current mepc
                        m.d.comb += cause.eq(ExceptionCause._COREBLOCKS_ASYNC_INTERRUPT)
                    with m.Else():  # TODO: tempor, will be simply replaced with misprediction exception
                        m.d.comb += exception.eq(0)
                        self.branch_verify_fifo.write(m, from_pc=0, next_pc=pc, resume_from_exception=0)

            with m.If(exception):
                report(m, rob_id=arg.rob_id, cause=cause, pc=pc)

            fifo.write(m, result=0, exception=exception, rob_id=arg.rob_id, rp_dst=arg.rp_dst)

        return m


class ExceptionUnitComponent(FunctionalComponentParams):
    def __init__(self):
        self.unit_fn = ExceptionUnitFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        unit = ExceptionFuncUnit(gen_params, self.unit_fn)
        gen_params.get(DependencyManager).add_dependency(BranchResolvedKey(), unit.branch_verify_fifo.read)
        return unit

    def get_optypes(self) -> set[OpType]:
        return self.unit_fn.get_op_types()
