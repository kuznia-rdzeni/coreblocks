from dataclasses import dataclass, KW_ONLY
from enum import IntFlag, auto
from typing import Sequence
from amaranth import *

from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, Funct3, Funct7
from transactron import TModule, def_method
from transactron.utils import OneHotSwitch
from coreblocks.func_blocks.interface.func_protocols import FuncUnit

from coreblocks.func_blocks.fu.common import DecoderManager, FuncUnitBase


class ZbsFn(DecoderManager):
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
    fn: ZbsFunction, in
        Function to be executed.
    in1: Signal(xlen), in
        First input.
    in2: Signal(xlen), in
        Second input.
    """

    def __init__(self, gen_params: GenParams, fn=ZbsFn()):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core generation parameters.
        function : ZbsFunction
            Decoder manager to decode instruction.
        """
        self.gen_params = gen_params

        self.xlen = gen_params.isa.xlen
        self.function = fn.get_function()
        self.in1 = Signal(self.xlen)
        self.in2 = Signal(self.xlen)

        self.result = Signal(self.xlen)

    def elaborate(self, platform):
        m = TModule()

        xlen_log = self.gen_params.isa.xlen_log

        with OneHotSwitch(m, self.function) as OneHotCase:
            with OneHotCase(ZbsFn.Fn.BCLR):
                m.d.comb += self.result.eq(self.in1 & ~(1 << self.in2[0:xlen_log]))
            with OneHotCase(ZbsFn.Fn.BEXT):
                m.d.comb += self.result.eq((self.in1 >> self.in2[0:xlen_log]) & 1)
            with OneHotCase(ZbsFn.Fn.BINV):
                m.d.comb += self.result.eq(self.in1 ^ (1 << self.in2[0:xlen_log]))
            with OneHotCase(ZbsFn.Fn.BSET):
                m.d.comb += self.result.eq(self.in1 | (1 << self.in2[0:xlen_log]))

        return m


class ZbsUnit(FuncUnitBase[ZbsFn]):
    """
    Executes Zbs instructions.
    """

    def __init__(self, gen_params: GenParams, fn=ZbsFn()):
        super().__init__(gen_params, fn)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.zbs = zbs = Zbs(self.gen_params, fn=self.fn)
        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)

        @def_method(m, self.issue)
        def _(arg):
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)

            m.d.av_comb += zbs.function.eq(decoder.decode_fn)
            m.d.av_comb += zbs.in1.eq(arg.s1_val)
            m.d.av_comb += zbs.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            self.push_result(m, rob_id=arg.rob_id, result=zbs.result, rp_dst=arg.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class ZbsComponent(FunctionalComponentParams):
    _: KW_ONLY
    decoder_manager: ZbsFn = ZbsFn()
    result_fifo: bool = True

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbsUnit(gen_params, self.decoder_manager)
