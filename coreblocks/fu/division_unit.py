from enum import IntFlag, IntEnum, auto
from typing import Sequence, Tuple
from dataclasses import KW_ONLY, dataclass

from amaranth import *

from coreblocks.fu.unsigned_multiplication.fast_recursive import RecursiveUnsignedMul
from coreblocks.fu.unsigned_multiplication.sequence import SequentialUnsignedMul
from coreblocks.fu.unsigned_multiplication.shift import ShiftUnsignedMul
from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.params import Funct3, GenParams, FuncUnitLayouts, OpType
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.fu.fu_decoder import DecoderManager

from coreblocks.utils import OneHotSwitch
from coreblocks.utils.protocols import FuncUnit


class DivFn(DecoderManager):
    class Fn(IntFlag):
        DIV = auto()
        DIVU = auto()
        REM = auto()
        REMU = auto()
        

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.DIV, OpType.DIV_REM, Funct3.DIV),
            (self.Fn.DIVU, OpType.DIV_REM, Funct3.DIVU),
            (self.Fn.REM, OpType.DIV_REM, Funct3.REM),
            (self.Fn.REMU, OpType.DIV_REM, Funct3.REMU),
        ]


def get_input(arg: Record) -> Tuple[Value, Value]:
    return arg.s1_val, Mux(arg.imm, arg.imm, arg.s2_val)



class DivUnit(FuncUnit, Elaboratable):
    """
    Module responsible for handling every kind of multiplication based on selected unsigned integer multiplication
    module. It uses standard FuncUnitLayout.

    Attributes
    ----------
    issue: Method(i=gen.get(FuncUnitLayouts).issue)
        Method used for requesting computation.
    accept: Method(i=gen.get(FuncUnitLayouts).accept)
        Method used for getting result of requested computation.
    """

    def __init__(self, gen_params: GenParams, div_fn=DivFn()):
        """
        Parameters
        ----------
        gen: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.div_fn = div_fn

    def elaborate(self, platform):
        m = TModule()

        m.submodules.result_fifo = result_fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.params_fifo = params_fifo = FIFO(
            [
                ("rob_id", self.gen_params.rob_entries_bits),
                ("rp_dst", self.gen_params.phys_regs_bits),
                ("negative_res", 1),
                ("high_res", 1),
            ],
            2,
        )
        m.submodules.decoder = decoder = self.div_fn.get_decoder(self.gen_params)

        # Selecting unsigned integer multiplication module
        m.submodules.divider = divider = ShiftUnsignedMul(self.gen_params)

        xlen = self.gen_params.isa.xlen
        sign_bit = xlen - 1  # position of sign bit
        # Prepared for RV64
        #
        # half_sign_bit = xlen // 2 - 1  # position of sign bit considering only half of input being used

        @def_method(m, self.accept)
        def _():
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            i1, i2 = get_input(arg)

            value1 = Signal(xlen)  # input value for multiplier submodule
            value2 = Signal(xlen)  # input value for multiplier submodule
            negative_res = Signal(1)  # if result is negative number
            rem_res = Signal(1)  # flag wheather we want result or reminder

            # Due to using unit multiplying unsigned integers, we need to convert input into two positive
            # integers, and later apply sign to result of this multiplication, also we need to save
            # which part of result we want upper or lower part. In the future, it would be a great improvement
            # to save result for chain multiplication of this same numbers, but with different parts as
            # results
            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(DivFn.Fn.DIV):  # MUL
                    m.d.comb += negative_res.eq(0)
                    m.d.comb += rem_res.eq(0)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with OneHotCase(DivFn.Fn.DIVU):
                    m.d.comb += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                    m.d.comb += rem_res.eq(0)
                    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.comb += value2.eq(Mux(i2[sign_bit], -i2, i2))
                with OneHotCase(DivFn.Fn.REM):
                    m.d.comb += negative_res.eq(0)
                    m.d.comb += rem_res.eq(1)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with OneHotCase(DivFn.Fn.REMU):
                    m.d.comb += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                    m.d.comb += rem_res.eq(1)
                    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.comb += value2.eq(Mux(i2[sign_bit], -i2, i2))

            params_fifo.write(m, rob_id=arg.rob_id, rp_dst=arg.rp_dst, negative_res=negative_res, high_res=rem_res)

            divider.issue(m, i1=value1, i2=value2)

        with Transaction().body(m):
            response = divider.accept(m)  # get result from unsigned multiplier
            params = params_fifo.read(m)
            sign_result = Mux(params.negative_res, -response.o, response.o)  # changing sign of result
            result = Mux(params.high_res, sign_result[xlen:], sign_result[:xlen])  # selecting upper or lower bits

            result_fifo.write(m, rob_id=params.rob_id, result=result, rp_dst=params.rp_dst)

        return m


@dataclass(frozen=True)
class MulComponent(FunctionalComponentParams):
    _: KW_ONLY
    dsp_width: int = 32
    div_fn = DivFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return DivUnit(gen_params, self.div_fn)

    def get_optypes(self) -> set[OpType]:
        return self.div_fn.get_op_types()
