from typing import Sequence, Type
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

__all__ = ["AluFuncUnit", "ALUComponent"]


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


def get_alu_fn(zba_enable: bool = False) -> Type[DecoderManager]:
    class AluFn(DecoderManager):
        Fn = Fn

        @classmethod
        def get_instructions(cls) -> Sequence[tuple]:
            return (
                [
                    (Fn.ADD, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
                    (Fn.SUB, OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
                    (Fn.SLT, OpType.COMPARE, Funct3.SLT),
                    (Fn.SLTU, OpType.COMPARE, Funct3.SLTU),
                    (Fn.XOR, OpType.LOGIC, Funct3.XOR),
                    (Fn.OR, OpType.LOGIC, Funct3.OR),
                    (Fn.AND, OpType.LOGIC, Funct3.AND),
                    (Fn.SLL, OpType.SHIFT, Funct3.SLL),
                    (Fn.SRL, OpType.SHIFT, Funct3.SR, Funct7.SL),
                    (Fn.SRA, OpType.SHIFT, Funct3.SR, Funct7.SA),
                ]
                + [
                    (Fn.SH1ADD, OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD),
                    (Fn.SH2ADD, OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD),
                    (Fn.SH3ADD, OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD),
                ]
                if zba_enable
                else []
            )

    return AluFn


class Alu(Elaboratable):
    def __init__(self, gen: GenParams, zba_enable: bool = False):
        self.gen = gen

        self.alu_fn = get_alu_fn(zba_enable=True)

        self.fn = self.alu_fn.get_function()
        self.in1 = Signal(gen.isa.xlen)
        self.in2 = Signal(gen.isa.xlen)

        self.out = Signal(gen.isa.xlen)

        self.zba_enable = zba_enable

    def elaborate(self, platform):
        m = Module()

        xlen = self.gen.isa.xlen
        xlen_log = self.gen.isa.xlen_log

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(Fn.ADD):
                m.d.comb += self.out.eq(self.in1 + self.in2)
            with OneHotCase(Fn.SLL):
                m.d.comb += self.out.eq(self.in1 << self.in2[0:xlen_log])
            with OneHotCase(Fn.XOR):
                m.d.comb += self.out.eq(self.in1 ^ self.in2)
            with OneHotCase(Fn.SRL):
                m.d.comb += self.out.eq(self.in1 >> self.in2[0:xlen_log])
            with OneHotCase(Fn.OR):
                m.d.comb += self.out.eq(self.in1 | self.in2)
            with OneHotCase(Fn.AND):
                m.d.comb += self.out.eq(self.in1 & self.in2)
            with OneHotCase(Fn.SUB):
                m.d.comb += self.out.eq(self.in1 - self.in2)
            with OneHotCase(Fn.SRA):
                m.d.comb += self.out.eq(Cat(self.in1, Repl(self.in1[xlen - 1], xlen)) >> self.in2[0:xlen_log])
            with OneHotCase(Fn.SLT):
                m.d.comb += self.out.eq(self.in1.as_signed() < self.in2.as_signed())
            with OneHotCase(Fn.SLTU):
                m.d.comb += self.out.eq(self.in1 < self.in2)

            if self.zba_enable:
                with OneHotCase(Fn.SH1ADD):
                    m.d.comb += self.out.eq((self.in1 << 1) + self.in2)
                with OneHotCase(Fn.SH2ADD):
                    m.d.comb += self.out.eq((self.in1 << 2) + self.in2)
                with OneHotCase(Fn.SH3ADD):
                    m.d.comb += self.out.eq((self.in1 << 3) + self.in2)

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class AluFuncUnit(Elaboratable):
    def __init__(self, gen: GenParams, zba_enable: bool = False):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.zba_enable = zba_enable

    def elaborate(self, platform):
        m = Module()

        m.submodules.alu = alu = Alu(self.gen, zba_enable=self.zba_enable)
        m.submodules.fifo = fifo = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = alu.alu_fn.get_decoder(self.gen)

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
    def __init__(self, zba_enable: bool = False):
        self.zba_enable = zba_enable

    def get_module(self, gen_params: GenParams, zba_enable: bool = False) -> AluFuncUnit:
        return AluFuncUnit(gen_params, zba_enable=zba_enable)

    def get_optypes(self) -> set[OpType]:
        return get_alu_fn().get_op_types()
