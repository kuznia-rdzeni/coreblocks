from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch

from enum import IntFlag


class DecoderManager(Signal):
    @unique
    class Fn(IntFlag):

        ADD = auto()  # Addition
        SLL = auto()  # Logic left shift
        XOR = auto()  # Bitwise xor
        SRL = auto()  # Logic right shift
        OR = auto()  # Bitwise or
        AND = auto()  # Bitwise and
        SUB = auto()  # Subtraction
        SRA = auto()  # Arithmetic right shift
        SLT = auto()  # Set if less than (signed)
        SLTU = auto()  # Set if less than (unsigned)
        # ZBA extension
        SH1ADD = auto()  # Logic left shift by 1 and add
        SH2ADD = auto()  # Logic left shift by 2 and add
        SH3ADD = auto()  # Logic left shift by 3 and add

    @classmethod
    def get_instrutions(cls):
        return [
            (cls.Fn.ADD, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
            (cls.Fn.SUB, OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
            (cls.Fn.SLT, OpType.COMPARE, Funct3.SLT),
            (cls.Fn.SLTU, OpType.COMPARE, Funct3.SLTU),
            (cls.Fn.XOR, OpType.LOGIC, Funct3.XOR),
            (cls.Fn.OR, OpType.LOGIC, Funct3.OR),
            (cls.Fn.AND, OpType.LOGIC, Funct3.AND),
            (cls.Fn.SLL, OpType.SHIFT, Funct3.SLL),
            (cls.Fn.SRL, OpType.SHIFT, Funct3.SR, Funct7.SL),
            (cls.Fn.SRA, OpType.SHIFT, Funct3.SR, Funct7.SA),
            (cls.Fn.SH1ADD, OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD),
            (cls.Fn.SH2ADD, OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD),
            (cls.Fn.SH3ADD, OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD),
        ]

    @classmethod
    def get_intruction_enum(cls):
        return cls.Fn

    @classmethod
    def get_op_types(cls):
        istr = cls.get_instrutions()

        op_types = set()

        for inst in istr:
            op_types.add(inst[1])

        return op_types

    @classmethod
    def get_decoder(cls, gen):
        return Decoder(gen, cls.Fn, cls.get_instrutions())

    def __init__(self, *args, **kwargs):
        super().__init__(DecoderManager.Fn, *args, **kwargs)


class Decoder(Elaboratable):
    def __init__(self, gen: GenParams, decode_fn, instructions):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.decode_fn = Signal(decode_fn)
        self.ops = instructions

    def elaborate(self, platform):
        m = Module()

        for op in self.ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2])
            if len(op) == 4:
                cond = cond & (self.exec_fn.funct7 == op[3])

            with m.If(cond):
                m.d.comb += self.decode_fn.eq(op[0])

        return m
