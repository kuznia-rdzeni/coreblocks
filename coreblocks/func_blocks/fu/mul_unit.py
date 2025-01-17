from enum import IntFlag, IntEnum, auto
from collections.abc import Sequence
from dataclasses import KW_ONLY, dataclass

from amaranth import *

from coreblocks.func_blocks.fu.unsigned_multiplication.fast_recursive import RecursiveUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.sequence import SequentialUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.shift import ShiftUnsignedMul
from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, Funct3
from coreblocks.interface.layouts import FuncUnitLayouts
from transactron import *
from transactron.core import def_method
from transactron.lib import *
from transactron.utils import MethodStruct


from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager


__all__ = ["MulUnit", "MulFn", "MulComponent", "MulType"]

from transactron.utils import OneHotSwitch
from coreblocks.func_blocks.interface.func_protocols import FuncUnit


class MulFn(DecoderManager):
    """
    Hot wire enum of 5 different multiplication operations.
    """

    class Fn(IntFlag):
        MUL = auto()  # Lower part multiplication
        MULH = auto()  # Upper part multiplication signed×signed
        MULHU = auto()  # Upper part multiplication unsigned×unsigned
        MULHSU = auto()  # Upper part multiplication signed×unsigned
        # Prepared for RV64
        #
        # MULW = auto()  # Multiplication of lower half of bits

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.MUL, OpType.MUL, Funct3.MUL),
            (self.Fn.MULH, OpType.MUL, Funct3.MULH),
            (self.Fn.MULHU, OpType.MUL, Funct3.MULHU),
            (self.Fn.MULHSU, OpType.MUL, Funct3.MULHSU),
        ]


def get_input(arg: MethodStruct) -> tuple[Value, Value]:
    """
    Operation of getting two input values.

    Parameters
    ----------
    arg: MethodStruct
        Arguments of functional unit issue call.

    Returns
    -------
    return : tuple[Value, Value]
        Two input values.
    """
    return arg.s1_val, Mux(arg.imm, arg.imm, arg.s2_val)


class MulType(IntEnum):
    """
    Enum of different multiplication units types
    """

    #: The cheapest multiplication unit in terms of resources, it uses Russian Peasants Algorithm.
    SHIFT_MUL = 0
    #: Uses single DSP unit for multiplication, which makes balance between performance and cost.
    SEQUENCE_MUL = 1
    #: Fastest way of multiplying using only one cycle, but costly in terms of resources.
    RECURSIVE_MUL = 2


class MulUnit(FuncUnit, Elaboratable):
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

    def __init__(self, gen_params: GenParams, mul_type: MulType, dsp_width: int = 32, mul_fn=MulFn()):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        self.mul_type = mul_type
        self.dsp_width = dsp_width

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.mul_fn = mul_fn

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
        m.submodules.decoder = decoder = self.mul_fn.get_decoder(self.gen_params)

        # Selecting unsigned integer multiplication module
        match self.mul_type:
            case MulType.SHIFT_MUL:
                m.submodules.multiplier = multiplier = ShiftUnsignedMul(self.gen_params)
            case MulType.SEQUENCE_MUL:
                m.submodules.multiplier = multiplier = SequentialUnsignedMul(self.gen_params, self.dsp_width)
            case MulType.RECURSIVE_MUL:
                m.submodules.multiplier = multiplier = RecursiveUnsignedMul(self.gen_params, self.dsp_width)

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
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)
            i1, i2 = get_input(arg)

            value1 = Signal(self.gen_params.isa.xlen)  # input value for multiplier submodule
            value2 = Signal(self.gen_params.isa.xlen)  # input value for multiplier submodule
            negative_res = Signal(1)  # if result is negative number
            high_res = Signal(1)  # if result should contain upper part of result

            # Due to using unit multiplying unsigned integers, we need to convert input into two positive
            # integers, and later apply sign to result of this multiplication, also we need to save
            # which part of result we want upper or lower part. In the future, it would be a great improvement
            # to save result for chain multiplication of this same numbers, but with different parts as
            # results
            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(MulFn.Fn.MUL):  # MUL
                    # In this case we care only about lower part of number, so it does not matter if it is
                    # interpreted as binary number or U2 encoded number, so we set result to be interpreted as
                    # non-negative number.
                    m.d.av_comb += negative_res.eq(0)
                    m.d.av_comb += high_res.eq(0)
                    m.d.av_comb += value1.eq(i1)
                    m.d.av_comb += value2.eq(i2)
                with OneHotCase(MulFn.Fn.MULH):
                    m.d.av_comb += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                    m.d.av_comb += high_res.eq(1)
                    m.d.av_comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.av_comb += value2.eq(Mux(i2[sign_bit], -i2, i2))
                with OneHotCase(MulFn.Fn.MULHU):
                    m.d.av_comb += negative_res.eq(0)
                    m.d.av_comb += high_res.eq(1)
                    m.d.av_comb += value1.eq(i1)
                    m.d.av_comb += value2.eq(i2)
                with OneHotCase(MulFn.Fn.MULHSU):
                    m.d.av_comb += negative_res.eq(i1[sign_bit])
                    m.d.av_comb += high_res.eq(1)
                    m.d.av_comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.av_comb += value2.eq(i2)
                # Prepared for RV64
                #
                # with OneHotCase(MulFn.Fn.MULW):
                #     m.d.comb += negative_res.eq(i1[half_sign_bit] ^ i2[half_sign_bit])
                #     m.d.comb += high_res.eq(0)
                #     i1h = Signal(xlen // 2)
                #     i2h = Signal(xlen // 2)
                #     m.d.comb += i1h.eq(Mux(i1[half_sign_bit], -i1, i1))
                #     m.d.comb += i2h.eq(Mux(i2[half_sign_bit], -i2, i2))
                #     m.d.comb += value1.eq(i1h)
                #     m.d.comb += value2.eq(i2h)

            params_fifo.write(m, rob_id=arg.rob_id, rp_dst=arg.rp_dst, negative_res=negative_res, high_res=high_res)

            multiplier.issue(m, i1=value1, i2=value2)

        with Transaction().body(m):
            response = multiplier.accept(m)  # get result from unsigned multiplier
            params = params_fifo.read(m)
            sign_result = Mux(params.negative_res, -response.o, response.o)  # changing sign of result
            result = Mux(params.high_res, sign_result[xlen:], sign_result[:xlen])  # selecting upper or lower bits

            result_fifo.write(m, rob_id=params.rob_id, result=result, rp_dst=params.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class MulComponent(FunctionalComponentParams):
    mul_unit_type: MulType
    _: KW_ONLY
    dsp_width: int = 32
    decoder_manager: MulFn = MulFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return MulUnit(gen_params, self.mul_unit_type, self.dsp_width, self.decoder_manager)
