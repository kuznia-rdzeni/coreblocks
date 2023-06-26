from typing import Sequence, Callable
from amaranth import *
from enum import IntFlag, auto

from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.utils._typing import ValueLike
from coreblocks.fu.fu_decoder import DecoderManager
from coreblocks.fu.vector_unit.utils import *

__all__ = ["FlexibleAdder", "FlexibleElementwiseFunction"]


class FlexibleAluFn(DecoderManager):
    class Fn(IntFlag):
        SUB = auto()  # Subtraction
        ADD = auto()  # Addition
        SRA = auto()  # Arithmetic right shift
        SLL = auto()  # Logic left shift
        SRL = auto()  # Logic right shift
        SLET = auto()  # Set if less or equal than (signed)
        SLETU = auto()  # Set if less or equal than (unsigned)
        SLT = auto()  # Set if less than (signed)
        SLTU = auto()  # Set if less than (unsigned)
        SEQ = auto()  # Set if equal
        XOR = auto()  # Bitwise xor
        OR = auto()  # Bitwise or
        AND = auto()  # Bitwise and

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
            # TODO fill after extending instruction decoder
        ]


class FlexibleAdder(Elaboratable):
    def __init__(self, out_width: EEW):
        self.out_width = out_width
        self.out_width_bits: int = eew_to_bits(out_width)
        self.eew = Signal(EEW)
        self.in1 = Signal(self.out_width_bits)
        self.in2 = Signal(self.out_width_bits)
        self.substract = Signal()

        self.out_data = Signal(self.out_width_bits)
        self.out_carry = Signal()

    def elaborate(self, platform) -> TModule:
        m = TModule()

        self.in2_trans = Signal.like(self.in2)
        with m.If(self.substract & (self.out_width == self.eew)):
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
                m.d.comb += adder.substract.eq(self.substract)

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
    def __init__(self, out_width : EEW, op : Callable[[ValueLike, ValueLike], ValueLike]):
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
            m.d.top_comb += appl_down.in1.eq(self.in1 & (2**smaller_out_width_bits-1))
            m.d.top_comb += appl_down.in2.eq(self.in2 & (2**smaller_out_width_bits-1))
            m.d.top_comb += appl_up.in1.eq(self.in1 >> smaller_out_width_bits)
            m.d.top_comb += appl_up.in2.eq(self.in2 >> smaller_out_width_bits)

            with m.If(self.eew == self.out_width):
                m.d.comb += self.out_data.eq(self.op(self.in1, self.in2))
            with m.Else():
                m.d.comb += self.out_data.eq((appl_up.out_data << smaller_out_width_bits) | appl_down.out_data)

        return m


def compress_mask(val : Value) -> Value:
    """
    Zakładamy że wartości są z ElementwiseFunction i setif... ustawijaą jeden, możemy więc wyciągnąć
    po prostu bity, bowiem jeśli element był służszy to mamy gwarancję, że na wyższych bitach będą zera.
    """
    return val[::8]

class BasicFlexibleAlu(Elaboratable):
    """
    FlexibleAlu without any hand-made optimisations.
    """

    def __init__(self, gen_params: GenParams, v_params: VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

        self.fn = FlexibleAluFn().get_function()
        self.eew = Signal(EEW)
        self.in1 = Signal(self.v_params.elen)
        self.in2 = Signal(self.v_params.elen)

    def elaborate(self, platform) -> TModule:
        m = TModule()
        # TODO Implement under separate PR
        return m
