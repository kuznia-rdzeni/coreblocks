from typing import Sequence
from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.isa import Funct3

from coreblocks.transactions import *
from coreblocks.transactions.lib import FIFO

from coreblocks.params import OpType, GenParams, FuncUnitLayouts, FunctionalComponentParams
from coreblocks.utils import OneHotSwitch
from coreblocks.params.keys import ExceptionRegisterKey

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.utils.protocols import FuncUnit

from coreblocks.structs_common.exception import Cause

__all__ = ["ExceptionFuncUnit"]


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

        dm = gen_params.get(DependencyManager)
        self.exception_register = dm.get_dependency(ExceptionRegisterKey())

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

            cause = Signal(Cause)

            with OneHotSwitch(m, self.fn.get_function()) as OneHotCase:
                with OneHotCase(ExceptionUnitFn.Fn.EBREAK):
                    m.d.comb += cause.eq(Cause.BREAKPOINT)
                with OneHotCase(ExceptionUnitFn.Fn.ECALL):
                    # TODO: Switch privilege level when implemented
                    m.d.comb += cause.eq(Cause.ENVIRONMENT_CALL_FROM_M)
                with OneHotCase(ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT):
                    m.d.comb += cause.eq(Cause.INSTRUCTION_ACCESS_FAULT)
                with OneHotCase(ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION):
                    m.d.comb += cause.eq(Cause.ILLEGAL_INSTRUCTION)
                with OneHotCase(ExceptionUnitFn.Fn.BREAKPOINT):
                    m.d.comb += cause.eq(Cause.BREAKPOINT)
                with OneHotCase(ExceptionUnitFn.Fn.INSTR_PAGE_FAULT):
                    m.d.comb += cause.eq(Cause.INSTRUCTION_PAGE_FAULT)

            self.exception_register.report(m, rob_id=arg.rob_id, cause=cause)

            fifo.write(m, result=0, exception=1, rob_id=arg.rob_id, rp_dst=arg.rp_dst)

        return m


class ShiftUnitComponent(FunctionalComponentParams):
    def __init__(self):
        self.unit_fn = ExceptionUnitFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ExceptionFuncUnit(gen_params, self.unit_fn)

    def get_optypes(self) -> set[OpType]:
        return self.unit_fn.get_op_types()
