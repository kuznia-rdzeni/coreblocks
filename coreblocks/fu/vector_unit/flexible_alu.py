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

    class Width(IntFlag):
        w8 = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
                #TODO fill after extending instruction decoder
        ]

class FlexibleAdder

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


