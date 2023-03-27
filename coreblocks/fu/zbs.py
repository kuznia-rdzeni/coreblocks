from enum import IntFlag
from typing import Sequence
from amaranth import *

from coreblocks.params import Funct3, GenParams, FuncUnitLayouts, OpType, Funct7, FunctionalComponentParams, auto
from coreblocks.transactions import Method
from coreblocks.transactions.lib import FIFO
from coreblocks.transactions.core import def_method
from coreblocks.utils import OneHotSwitch
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

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
            (cls.Fn.BCLR, OpType.SINGLE_BIT_MANIPULATION, Funct3.BCLR, Funct7.BCLR),
            (cls.Fn.BEXT, OpType.SINGLE_BIT_MANIPULATION, Funct3.BEXT, Funct7.BEXT),
            (cls.Fn.BINV, OpType.SINGLE_BIT_MANIPULATION, Funct3.BINV, Funct7.BINV),
            (cls.Fn.BSET, OpType.SINGLE_BIT_MANIPULATION, Funct3.BSET, Funct7.BSET),
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

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.xlen = gen_params.isa.xlen
        self.function = ZbsFunction.get_function()
        self.in1 = Signal(self.xlen)
        self.in2 = Signal(self.xlen)

        self.result = Signal(self.xlen)

    def elaborate(self, platform):
        m = Module()

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


class ZbsUnit(Elaboratable):
    """
    Module responsible for executing Zbs instructions.

    Attributes
    ----------
    issue: Method(i=FuncUnitLayouts.issue)
        Method used for requesting computation.
    accept: Method(i=FuncUnitLayouts.accept)
        Method used for getting result of requested computation.
    """

    optypes = ZbsFunction.get_op_types()

    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(FuncUnitLayouts)

        self.gen_params = gen_params
        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.zbs = zbs = Zbs(self.gen_params)
        m.submodules.result_fifo = result_fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = ZbsFunction.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _(arg):
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            m.d.comb += zbs.function.eq(decoder.decode_fn)
            m.d.comb += zbs.in1.eq(arg.s1_val)
            m.d.comb += zbs.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            result_fifo.write(m, rob_id=arg.rob_id, result=zbs.result, rp_dst=arg.rp_dst)

        return m


class ZbsComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbsUnit(gen_params)

    def get_optypes(self) -> set[OpType]:
        return ZbsUnit.optypes
