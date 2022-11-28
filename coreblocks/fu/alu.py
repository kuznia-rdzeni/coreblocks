from amaranth import *

from enum import IntEnum, unique

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *

__all__ = ["AluFuncUnit"]


class AluFn(Signal):
    @unique
    class Fn(IntEnum):
        ADD = 1 << 0  # Addition
        SLL = 1 << 1  # Logic left shift
        XOR = 1 << 2  # Bitwise xor
        SRL = 1 << 3  # Logic right shift
        OR = 1 << 4  # Bitwise or
        AND = 1 << 5  # Bitwise and
        SUB = 1 << 6  # Subtraction
        SRA = 1 << 7  # Arithmetic right shift
        SLT = 1 << 8  # Set if less than (signed)
        SLTU = 1 << 9  # Set if less than (unsigned)

    def __init__(self, *args, **kwargs):
        super().__init__(AluFn.Fn, *args, **kwargs)


class Alu(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

        self.fn = AluFn()
        self.in1 = Signal(gen.isa.xlen)
        self.in2 = Signal(gen.isa.xlen)

        self.out = Signal(gen.isa.xlen)

    def elaborate(self, platform):
        m = Module()

        xlen = self.gen.isa.xlen
        xlen_log = self.gen.isa.xlen_log

        with m.Switch(self.fn):
            with m.Case(AluFn.Fn.ADD):
                m.d.comb += self.out.eq(self.in1 + self.in2)
            with m.Case(AluFn.Fn.SLL):
                m.d.comb += self.out.eq(self.in1 << self.in2[0:xlen_log])
            with m.Case(AluFn.Fn.XOR):
                m.d.comb += self.out.eq(self.in1 ^ self.in2)
            with m.Case(AluFn.Fn.SRL):
                m.d.comb += self.out.eq(self.in1 >> self.in2[0:xlen_log])
            with m.Case(AluFn.Fn.OR):
                m.d.comb += self.out.eq(self.in1 | self.in2)
            with m.Case(AluFn.Fn.AND):
                m.d.comb += self.out.eq(self.in1 & self.in2)
            with m.Case(AluFn.Fn.SUB):
                m.d.comb += self.out.eq(self.in1 - self.in2)
            with m.Case(AluFn.Fn.SRA):
                m.d.comb += self.out.eq(Cat(self.in1, Repl(self.in1[xlen - 1], xlen)) >> self.in2[0:xlen_log])
            with m.Case(AluFn.Fn.SLT):
                m.d.comb += self.out.eq(self.in1.as_signed() < self.in2.as_signed())
            with m.Case(AluFn.Fn.SLTU):
                m.d.comb += self.out.eq(self.in1 < self.in2)

            with m.Default():
                m.d.comb += self.out.eq(0)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class AluFnDecoder(Elaboratable):
    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.alu_fn = Signal(AluFn.Fn)

    def elaborate(self, platform):
        m = Module()

        ops = [
            (AluFn.Fn.ADD, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
            (AluFn.Fn.SUB, OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
            (AluFn.Fn.SLT, OpType.COMPARE, Funct3.SLT),
            (AluFn.Fn.SLTU, OpType.COMPARE, Funct3.SLTU),
            (AluFn.Fn.XOR, OpType.LOGIC, Funct3.XOR),
            (AluFn.Fn.OR, OpType.LOGIC, Funct3.OR),
            (AluFn.Fn.AND, OpType.LOGIC, Funct3.AND),
            (AluFn.Fn.SLL, OpType.SHIFT, Funct3.SLL),
            (AluFn.Fn.SRL, OpType.SHIFT, Funct3.SR, Funct7.SL),
            (AluFn.Fn.SRA, OpType.SHIFT, Funct3.SR, Funct7.SA),
        ]

        for op in ops:
            cond = (self.exec_fn.op_type == op[1]) & (self.exec_fn.funct3 == op[2])
            if len(op) == 4:
                cond = cond & (self.exec_fn.funct7 == op[3])

            with m.If(cond):
                m.d.comb += self.alu_fn.eq(op[0])

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
        m.submodules.decoder = decoder = AluFnDecoder(self.gen)

        @def_method(m, self.accept)
        def _(arg):
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.comb += alu.fn.eq(decoder.alu_fn)

            m.d.comb += alu.in1.eq(arg.s1_val)
            m.d.comb += alu.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            fifo.write(m, arg={"rob_id": arg.rob_id, "result": alu.out, "rp_dst": arg.rp_dst})

        return m
