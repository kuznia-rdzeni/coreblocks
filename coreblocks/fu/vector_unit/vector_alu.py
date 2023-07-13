from amaranth import *
from enum import IntFlag, auto
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.fu_decoder import DecoderManager

__all__ = ["VectorBasicFlexibleAlu"]

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


class VectorBasicFlexibleAlu(Elaboratable):
    """
    FlexibleAlu without any hand-made optimisations.

    TODO
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
