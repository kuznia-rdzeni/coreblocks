from typing import Sequence
from amaranth import *
from transactron.utils.dependencies import DependencyContext

from transactron import *
from transactron.lib import FIFO

from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, Funct3, ExceptionCause
from coreblocks.interface.layouts import FuncUnitLayouts
from transactron.utils import OneHotSwitch
from coreblocks.interface.keys import ExceptionReportKey

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.func_blocks.interface.func_protocols import FuncUnit

__all__ = ["ExceptionFuncUnit", "ExceptionUnitComponent"]


class ExceptionUnitFn(DecoderManager):
    class Fn(IntFlag):
        ECALL = auto()
        EBREAK = auto()
        # Fns representing exceptions caused by instructions before FUs
        INSTR_ACCESS_FAULT = auto()
        ILLEGAL_INSTRUCTION = auto()
        BREAKPOINT = auto()
        INSTR_PAGE_FAULT = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.ECALL, OpType.ECALL),
            (self.Fn.EBREAK, OpType.EBREAK),
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

        dm = DependencyContext.get()
        self.report = dm.get_dependency(ExceptionReportKey())

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            cause = Signal(ExceptionCause)

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

            self.report(m, rob_id=arg.rob_id, cause=cause, pc=arg.pc)

            fifo.write(m, result=0, exception=1, rob_id=arg.rob_id, rp_dst=arg.rp_dst)

        return m


class ExceptionUnitComponent(FunctionalComponentParams):
    def __init__(self):
        self.unit_fn = ExceptionUnitFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        unit = ExceptionFuncUnit(gen_params, self.unit_fn)
        return unit

    def get_optypes(self) -> set[OpType]:
        return self.unit_fn.get_op_types()
