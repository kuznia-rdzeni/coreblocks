from typing import Sequence
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

__all__ = ["AluFuncUnit", "ALUComponent"]

from coreblocks.utils.protocols import FuncUnit


class AluFn(DecoderManager):
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
    def get_instructions(cls) -> Sequence[tuple]:
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


class Alu(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        self.fn = AluFn.get_function()
        self.in1 = Signal(gen.isa.xlen)
        self.in2 = Signal(gen.isa.xlen)

        self.out = Signal(gen.isa.xlen)

    def elaborate(self, platform):
        m = Module()

        xlen = self.gen.isa.xlen
        xlen_log = self.gen.isa.xlen_log

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(AluFn.Fn.ADD):
                m.d.comb += self.out.eq(self.in1 + self.in2)
            with OneHotCase(AluFn.Fn.SLL):
                m.d.comb += self.out.eq(self.in1 << self.in2[0:xlen_log])
            with OneHotCase(AluFn.Fn.XOR):
                m.d.comb += self.out.eq(self.in1 ^ self.in2)
            with OneHotCase(AluFn.Fn.SRL):
                m.d.comb += self.out.eq(self.in1 >> self.in2[0:xlen_log])
            with OneHotCase(AluFn.Fn.OR):
                m.d.comb += self.out.eq(self.in1 | self.in2)
            with OneHotCase(AluFn.Fn.AND):
                m.d.comb += self.out.eq(self.in1 & self.in2)
            with OneHotCase(AluFn.Fn.SUB):
                m.d.comb += self.out.eq(self.in1 - self.in2)
            with OneHotCase(AluFn.Fn.SRA):
                m.d.comb += self.out.eq(Cat(self.in1, Repl(self.in1[xlen - 1], xlen)) >> self.in2[0:xlen_log])
            with OneHotCase(AluFn.Fn.SLT):
                m.d.comb += self.out.eq(self.in1.as_signed() < self.in2.as_signed())
            with OneHotCase(AluFn.Fn.SLTU):
                m.d.comb += self.out.eq(self.in1 < self.in2)
            with OneHotCase(AluFn.Fn.SH1ADD):
                m.d.comb += self.out.eq((self.in1 << 1) + self.in2)
            with OneHotCase(AluFn.Fn.SH2ADD):
                m.d.comb += self.out.eq((self.in1 << 2) + self.in2)
            with OneHotCase(AluFn.Fn.SH3ADD):
                m.d.comb += self.out.eq((self.in1 << 3) + self.in2)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class AluFuncUnit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.alu = alu = Alu(self.gen)
        m.submodules.fifo = fifo = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = AluFn.get_decoder(self.gen)

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.comb += alu.fn.eq(decoder.decode_fn)

            m.d.comb += alu.in1.eq(arg.s1_val)
            m.d.comb += alu.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            fifo.write(m, rob_id=arg.rob_id, result=alu.out, rp_dst=arg.rp_dst)

        return m


class ALUComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return AluFuncUnit(gen_params)

    def get_optypes(self) -> set[OpType]:
        return AluFn.get_op_types()
