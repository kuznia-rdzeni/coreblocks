from amaranth import *

from enum import IntEnum, unique

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.lib import *

from coreblocks.genparams import GenParams

from coreblocks.transactions._utils import *

__all__ = ["AluOp", "Alu", "FuncUnitLayouts", "AluFuncUnit"]


class AluOp(Signal):
    @unique
    class Op(IntEnum):
        ADD = 0  # Addition
        SLL = 1  # Logic left shift
        SEQ = 2  # Set if equal
        SNE = 3  # Set if not equal
        XOR = 4  # Bitwise xor
        SRL = 5  # Logic right shift
        OR = 6  # Bitwise or
        AND = 7  # Bitwise and
        SUB = 10  # Subtraction
        SRA = 11  # Arithmetic right shift
        SLT = 12  # Set if less than (signed)
        SGE = 13  # Set if greater than or equal to (signed)
        SLTU = 14  # Set if less than (unsigned)
        SGEU = 15  # Set if greater than or equal to (unsigned)

    def __init__(self, *args, **kwargs):
        super().__init__(AluOp.Op, *args, **kwargs)


class Alu(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        self.op = AluOp()
        self.in1 = Signal(gen.isa.xlen)
        self.in2 = Signal(gen.isa.xlen)

        self.out = Signal(gen.isa.xlen)

    def elaborate(self, platform):
        m = Module()

        xlen = self.gen.isa.xlen
        xlen_log = self.gen.isa.xlen_log

        with m.Switch(self.op):
            with m.Case(AluOp.Op.ADD):
                m.d.comb += self.out.eq(self.in1 + self.in2)
            with m.Case(AluOp.Op.SLL):
                m.d.comb += self.out.eq(self.in1 << self.in2[0:xlen_log])
            with m.Case(AluOp.Op.SEQ):
                m.d.comb += self.out.eq(self.in1 == self.in2)
            with m.Case(AluOp.Op.SNE):
                m.d.comb += self.out.eq(self.in1 != self.in2)
            with m.Case(AluOp.Op.XOR):
                m.d.comb += self.out.eq(self.in1 ^ self.in2)
            with m.Case(AluOp.Op.SRL):
                m.d.comb += self.out.eq(self.in1 >> self.in2[0:xlen_log])
            with m.Case(AluOp.Op.OR):
                m.d.comb += self.out.eq(self.in1 | self.in2)
            with m.Case(AluOp.Op.AND):
                m.d.comb += self.out.eq(self.in1 & self.in2)
            with m.Case(AluOp.Op.SUB):
                m.d.comb += self.out.eq(self.in1 - self.in2)
            with m.Case(AluOp.Op.SRA):
                m.d.comb += self.out.eq(Cat(self.in1, Repl(self.in1[xlen - 1], xlen)) >> self.in2[0:xlen_log])
            with m.Case(AluOp.Op.SLT):
                m.d.comb += self.out.eq(self.in1.as_signed() < self.in2.as_signed())
            with m.Case(AluOp.Op.SGE):
                m.d.comb += self.out.eq(self.in1.as_signed() >= self.in2.as_signed())
            with m.Case(AluOp.Op.SLTU):
                m.d.comb += self.out.eq(self.in1 < self.in2)
            with m.Case(AluOp.Op.SGEU):
                m.d.comb += self.out.eq(self.in1 >= self.in2)

            with m.Default():
                m.d.comb += self.out.eq(0)

        return m


class FuncUnitLayouts:
    def __init__(self, gen: GenParams):
        self.issue = [
            ("rob_id", gen.rob_entries_bits),
            ("data1", gen.isa.xlen),
            ("data2", gen.isa.xlen),
            ("op", AluOp.Op),
        ]

        self.accept = [
            ("rob_id", gen.rob_entries_bits),
            ("result", gen.isa.xlen),
        ]


class AluFuncUnit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.alu = alu = Alu(self.gen)
        m.submodules.pipe = pipe = Pipe(self.gen.get(FuncUnitLayouts).accept)

        @def_method(m, self.accept, ready=pipe.sink.valid)
        def _(arg):
            m.d.comb += pipe.sink.ready.eq(1)

            return pipe.sink.payload

        @def_method(m, self.issue, ready=pipe.source.ready)
        def _(arg):
            m.d.comb += alu.op.eq(arg.op)
            m.d.comb += alu.in1.eq(arg.data1)
            m.d.comb += alu.in2.eq(arg.data2)

            m.d.comb += pipe.source.payload.result.eq(alu.out)
            m.d.comb += pipe.source.payload.rob_id.eq(arg.rob_id)

            m.d.comb += pipe.source.valid.eq(1)

        return m
