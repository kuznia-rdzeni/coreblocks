from typing import Sequence
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import FIFO

from coreblocks.params import OpType, GenParams, FuncUnitLayouts, FunctionalComponentParams
from coreblocks.utils import OneHotSwitch

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.utils.protocols import FuncUnit

__all__ = ["ExceptionFuncUnit"]


class ExceptionUnitFn(DecoderManager):
    class Fn(IntFlag):
        EXCEPTION = auto()
        ECALL = auto()
        EBREAK = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.EXCEPTION, OpType.EXCEPTION),
            (self.Fn.ECALL, OpType.ECALL),
            (self.Fn.EBREAK, OpType.EBREAK),
        ]


class ExceptionFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, unit_fn=ExceptionUnitFn()):
        self.gen_params = gen_params
        self.fn = unit_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

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

            with OneHotSwitch(m, self.fn.get_function()) as OneHotCase:
                with OneHotCase(ExceptionUnitFn.Fn.EBREAK):
                    pass
                with OneHotCase(ExceptionUnitFn.Fn.EBREAK):
                    pass

            fifo.write(m, result=0, exception=1, rob_id=arg.rob_id, rp_dst=arg.rp_dst)

        return m


class ShiftUnitComponent(FunctionalComponentParams):
    def __init__(self):
        self.unit_fn = ExceptionUnitFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ExceptionFuncUnit(gen_params, self.unit_fn)

    def get_optypes(self) -> set[OpType]:
        return self.unit_fn.get_op_types()
