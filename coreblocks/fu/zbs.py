from enum import IntFlag, auto
from typing import Sequence
from amaranth import *

from coreblocks.params import Funct3, GenParams, FuncUnitLayouts, OpType, Funct7, FunctionalComponentParams
from transactron import Method, TModule, def_method
from transactron.core import Priority
from coreblocks.utils import OneHotSwitch
from coreblocks.utils.fifo import BasicFifo
from coreblocks.utils.protocols import FuncUnit

from coreblocks.fu.fu_decoder import DecoderManager


class ZbsFunction(DecoderManager):
    """
    Enum of Zbs functions.
    """

    class Fn(IntFlag):
        BCLR = auto()  # Bit clear
        BEXT = auto()  # Bit extract
        BINV = auto()  # Bit invert
        BSET = auto()  # Bit set

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.BCLR, OpType.SINGLE_BIT_MANIPULATION, Funct3.BCLR, Funct7.BCLR),
            (self.Fn.BEXT, OpType.SINGLE_BIT_MANIPULATION, Funct3.BEXT, Funct7.BEXT),
            (self.Fn.BINV, OpType.SINGLE_BIT_MANIPULATION, Funct3.BINV, Funct7.BINV),
            (self.Fn.BSET, OpType.SINGLE_BIT_MANIPULATION, Funct3.BSET, Funct7.BSET),
        ]


class Zbs(Elaboratable):
    """
    Module responsible for executing Zbs instructions.

    Attributes
    ----------
    function: ZbsFunction, in
        Function to be executed.
    in1: Signal(xlen), in
        First input.
    in2: Signal(xlen), in
        Second input.

    Args:
    ----
        gen_params: Core generation parameters.
    """

    def __init__(self, gen_params: GenParams, function=ZbsFunction()):
        self.gen_params = gen_params

        self.xlen = gen_params.isa.xlen
        self.function = function.get_function()
        self.in1 = Signal(self.xlen)
        self.in2 = Signal(self.xlen)

        self.result = Signal(self.xlen)

    def elaborate(self, platform):
        m = TModule()

        xlen_log = self.gen_params.isa.xlen_log

        with OneHotSwitch(m, self.function) as OneHotCase:
            with OneHotCase(ZbsFunction.Fn.BCLR):
                m.d.comb += self.result.eq(self.in1 & ~(1 << self.in2[0:xlen_log]))
            with OneHotCase(ZbsFunction.Fn.BEXT):
                m.d.comb += self.result.eq((self.in1 >> self.in2[0:xlen_log]) & 1)
            with OneHotCase(ZbsFunction.Fn.BINV):
                m.d.comb += self.result.eq(self.in1 ^ (1 << self.in2[0:xlen_log]))
            with OneHotCase(ZbsFunction.Fn.BSET):
                m.d.comb += self.result.eq(self.in1 | (1 << self.in2[0:xlen_log]))

        return m


class ZbsUnit(FuncUnit, Elaboratable):
    """
    Module responsible for executing Zbs instructions.

    Attributes
    ----------
    issue: Method(i=FuncUnitLayouts.issue)
        Method used for requesting computation.
    accept: Method(i=FuncUnitLayouts.accept)
        Method used for getting result of requested computation.
    """

    def __init__(self, gen_params: GenParams, zbs_fn=ZbsFunction()):
        layouts = gen_params.get(FuncUnitLayouts)

        self.gen_params = gen_params
        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.clear = Method()

        self.zbs_fn = zbs_fn

    def elaborate(self, platform):
        m = TModule()

        m.submodules.zbs = zbs = Zbs(self.gen_params, function=self.zbs_fn)
        m.submodules.result_fifo = result_fifo = BasicFifo(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.zbs_fn.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _(arg):
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            m.d.comb += zbs.function.eq(decoder.decode_fn)
            m.d.comb += zbs.in1.eq(arg.s1_val)
            m.d.comb += zbs.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            result_fifo.write(m, rob_id=arg.rob_id, result=zbs.result, rp_dst=arg.rp_dst, exception=0)

        self.clear.proxy(m, result_fifo.clear)
        self.clear.add_conflict(self.issue, priority=Priority.LEFT)
        self.clear.add_conflict(self.accept, priority=Priority.LEFT)

        return m


class ZbsComponent(FunctionalComponentParams):
    def __init__(self):
        self.zbs_fn = ZbsFunction()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbsUnit(gen_params, self.zbs_fn)

    def get_optypes(self) -> set[OpType]:
        return self.zbs_fn.get_op_types()
