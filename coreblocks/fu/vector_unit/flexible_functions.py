from typing import Sequence, Callable
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.utils._typing import ValueLike

__all__ = ["FlexibleAdder", "FlexibleElementwiseFunction"]


class FlexibleAdder(Elaboratable):
    """Adder with support for different operand lengths

    This adder processes `out_width` bits in each cycle and it interprets them either
    as an operand with `out_width` bits or as a `k` operands each with
    `out_width//k`, width where `k` is power of two.

    All processing is done in one cycle. If the `out_width` of FlexibleAdder is greater
    than 8, then recursion will be used to create submodules, each processing half
    of the input. Next, carry bit of lower part is taken into account and the result can be
    incremented by it at each recurence level (which is potentially sub-optimal).

    Attributes
    ----------
    eew : Signal(EEW)
        EEW of the operands which are being processed
    in1 : Signal(out_width_bits)
        First operand
    in2 : Signal(out_width_bits)
        Second operand
    subtract : Signal()
        Instead of adding the second operand, subtract it from the first.
    out_data : Signal(out_width_bits)
        Output of the operation
    out_carry : Signal()
        Carry bit
    """

    def __init__(self, out_width: EEW):
        """
        Parameters
        ----------
        out_width : EEW
            The width of the operands and result that this adder should operate on.
        """
        self.out_width = out_width
        self.out_width_bits: int = eew_to_bits(out_width)
        self.eew = Signal(EEW)
        self.in1 = Signal(self.out_width_bits)
        self.in2 = Signal(self.out_width_bits)
        self.subtract = Signal()

        self.out_data = Signal(self.out_width_bits)
        self.out_carry = Signal()

    def elaborate(self, platform) -> TModule:
        m = TModule()

        self.in2_trans = Signal.like(self.in2)
        with m.If(self.subtract & (self.out_width == self.eew)):
            m.d.comb += self.in2_trans.eq((~self.in2) + 1)
        with m.Else():
            m.d.comb += self.in2_trans.eq(self.in2)

        if self.out_width == EEW.w8:
            result = self.in1 + self.in2_trans
            assert result.shape().width == self.out_width_bits + 1
            m.d.comb += self.out_data.eq(result & (2**self.out_width_bits - 1))
            m.d.comb += self.out_carry.eq(result >> self.out_width_bits)
        else:
            smaller_out_width_bits = self.out_width_bits // 2
            smaller_out_width_eew = bits_to_eew(smaller_out_width_bits)
            m.submodules.adder_down = adder_down = FlexibleAdder(smaller_out_width_eew)
            m.submodules.adder_high = adder_high = FlexibleAdder(smaller_out_width_eew)

            for adder in {adder_down, adder_high}:
                m.d.comb += adder.eew.eq(self.eew)
                m.d.comb += adder.subtract.eq(self.subtract)

            m.d.comb += adder_down.in1.eq(self.in1 & (2**smaller_out_width_bits - 1))
            m.d.comb += adder_down.in2.eq(self.in2_trans & (2**smaller_out_width_bits - 1))
            m.d.comb += adder_high.in1.eq(self.in1 >> smaller_out_width_bits)
            m.d.comb += adder_high.in2.eq(self.in2_trans >> smaller_out_width_bits)

            with m.If(self.eew >= self.out_width):
                whole_high = (adder_high.out_carry << smaller_out_width_bits) | adder_high.out_data
                high_with_down_carry = whole_high + adder_down.out_carry
                result = (high_with_down_carry << smaller_out_width_bits) | adder_down.out_data
                m.d.comb += self.out_data.eq(result & (2**self.out_width_bits - 1))
                m.d.comb += self.out_carry.eq(result >> self.out_width_bits)
            with m.Else():
                result = (adder_high.out_data << smaller_out_width_bits) | adder_down.out_data
                m.d.comb += self.out_data.eq(result)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class FlexibleElementwiseFunction(Elaboratable):
    """Generic implementation of element-wise functions with support for different operands lengths

    This module provides a generic way to create a block which will process `out_bits`
    in each cycle by interpreting them as a single element of width `out_bits` or as a
    set of `k` elements each with length `out_bits//k` where `k` is power of 2. It applies on
    each pair of operands the `op` function, which takes two arguments and returns a result of
    the same width as the arguments.

    Any two argument function can be passed as `op`, but the user should be aware that
    hardware computing `op` is synthesised at each recursion level of the `FlexibleElementwiseFunction`,
    so usage of synthetised `op` block will be in some cases non-optimal.

    This module can be used to implement adder similar to `FlexibleAdder`, but using larger number
    of hardware adders.

    Attributes
    ----------
    op : Callable[[ValueLike, ValueLike], ValueLike]
        Function to be applied ro operands separated from `in1` and `in2`.
    eew : Signal(EEW)
        Width of the currently processed inputs
    in1 : Signal(out_width_bits)
        First operand
    in2 : Signal(out_width_bits)
        Second operand
    out_data : Signal(out_width_bits)
        Results of the application `op` on `in1` and `in2`.
    """

    def __init__(self, out_width: EEW, op: Callable[[ValueLike, ValueLike], ValueLike]):
        """
        Parameters
        ----------
        out_width : EEW
            Maximum supported width of operands.
        op : Callable[[ValueLike, ValueLike], ValueLike]
            Function to be applied over operands.
        """
        self.out_width = out_width
        self.op = op
        self.out_width_bits: int = eew_to_bits(out_width)
        self.eew = Signal(EEW)
        self.in1 = Signal(self.out_width_bits)
        self.in2 = Signal(self.out_width_bits)
        self.out_data = Signal(self.out_width_bits)

    def elaborate(self, platform):
        m = TModule()

        if self.out_width == EEW.w8:
            m.d.comb += self.out_data.eq(self.op(self.in1, self.in2))
        else:
            smaller_out_width_bits = self.out_width_bits // 2

            m.submodules.applicator_down = appl_down = FlexibleElementwiseFunction(eew_div_2(self.out_width), self.op)
            m.submodules.applicator_up = appl_up = FlexibleElementwiseFunction(eew_div_2(self.out_width), self.op)

            m.d.top_comb += appl_down.eew.eq(self.eew)
            m.d.top_comb += appl_up.eew.eq(self.eew)
            m.d.top_comb += appl_down.in1.eq(self.in1 & (2**smaller_out_width_bits - 1))
            m.d.top_comb += appl_down.in2.eq(self.in2 & (2**smaller_out_width_bits - 1))
            m.d.top_comb += appl_up.in1.eq(self.in1 >> smaller_out_width_bits)
            m.d.top_comb += appl_up.in2.eq(self.in2 >> smaller_out_width_bits)

            with m.If(self.eew == self.out_width):
                m.d.comb += self.out_data.eq(self.op(self.in1, self.in2))
            with m.Else():
                m.d.comb += self.out_data.eq((appl_up.out_data << smaller_out_width_bits) | appl_down.out_data)

        return m


def compress_mask(m: TModule, val: Value, eew: Value) -> Value:
    """Compress masks created with `FlexibleElementwiseFunction`

    This function takes `val` with `out_width_bits` from `FlexibleElementwiseFunction` and
    assumes that mask bits are set on the first bit of each output element. As an output it
    returns the mask compressed to one bit per bajt. If operands where processed
    with element eew bigger the EEW.w8, then only the first `k` bits are valid, where
    `k = out_width/eew`.

    Parameters
    ----------
    m : TModule
        Module to which the computations should be connected
    val : Value
        Output to be compressed into mask format
    eew : Value(EEW)
        EEW used to generate `val`
    """
    result = Signal(len(val) // 8)
    with m.Switch(eew):
        for i in EEW:
            with m.Case(EEW(i)):
                m.d.top_comb += result.eq(val[:: eew_to_bits(EEW(i))])
    return result
