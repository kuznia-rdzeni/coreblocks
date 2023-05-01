from typing import Sequence
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.utils.protocols import FuncUnit
from coreblocks.fu.vector_unit.utils import EEW

__all__ = ["EEW"]


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
        SEQ = auto() # Set if equal
        XOR = auto()  # Bitwise xor
        OR = auto()  # Bitwise or
        AND = auto()  # Bitwise and

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
                #TODO fill after extending instruction decoder
        ]

class FlexibleAdder(Elaboratable):
    def __init__(self, v_params : VectorParameters, out_width : EEW):
        self.v_params = v_params
        self.out_width = out_width
        self.out_width_bits : int = transform(out_width)
        self.eew = Signal(EEW)
        self.in1 = Signal(self.out_width_bits)
        self.in2 = Signal(self.out_width_bits)

        self.out_data = Signal(self.out_width_bits)
        self.out_carry = Signal()

    def elaborate(self, platform) -> Module:
        m = Module()

        if self.out_width == EEW.w8:
            result = self.in1 + self.in2
            assert result.shape().width == self.out_width_bits+1
            m.d.comb += self.out_data.eq(result[:-1])
            m.d.comb += self.out_carry.eq(result[-1])
        else:
            smaller_out_width = TODO
            #TODO connect self.EEW, in1, in2
            m.submodules.adder_down = adder_down = FlexibleAdder(self.v_params, smaller_out_width)
            m.submodules.adder_high = adder_high = FlexibleAdder(self.v_params, smaller_out_width)

            with m.If(self.eew <= self.out_width):
                high_with_down_carry = whole_high + adder_down.out_carry
                result = (high_with_down_carry << bits_smaller) | adder_down.out_data
                m.d.comb += self.out_data.eq(result[:-1])
                m.d.comb += self.out_carry.eq(result[-1])
            with m.Else():
                result = Cat(adder_high.out_data, adder_down.out_data)
                m.d.comb += self.out_data.eq(result[:-1])

        return m

class BasicFlexibleAlu(Elaboratable):
    """
    FlexibleAlu without any hand-made optimisations.
    """
    def __init__(self, gen_params: GenParams, v_params : VectorParameters):
        self.gen_params = gen_params
        self.v_params = v_params

        self.fn = FlexibleAluFn.get_function()
        self.eew = Signal(EEW)
        self.in1 = Signal(self.v_params.elen)
        self.in2 = Signal(self.v_params.elen)

    def elaborate(self, platform):
        m = Module()


