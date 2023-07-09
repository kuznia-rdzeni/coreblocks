from typing import Sequence
from amaranth import *

from transactron import *
from transactron.core import Priority

from coreblocks.params import OpType, Funct3, Funct7, GenParams, FuncUnitLayouts, FunctionalComponentParams
from coreblocks.utils import HasElaborate, OneHotSwitch
from coreblocks.utils.fifo import BasicFifo

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.utils.protocols import FuncUnit

from coreblocks.utils.utils import popcount, count_leading_zeros

__all__ = ["AluFuncUnit", "ALUComponent"]


class AluFn(DecoderManager):
    def __init__(self, zba_enable=False, zbb_enable=False) -> None:
        self.zba_enable = zba_enable
        self.zbb_enable = zbb_enable

    class Fn(IntFlag):
        ADD = auto()  # Addition
        XOR = auto()  # Bitwise xor
        OR = auto()  # Bitwise or
        AND = auto()  # Bitwise and
        SUB = auto()  # Subtraction
        SLT = auto()  # Set if less than (signed)
        SLTU = auto()  # Set if less than (unsigned)

        # ZBA extension
        SH1ADD = auto()  # Logic left shift by 1 and add
        SH2ADD = auto()  # Logic left shift by 2 and add
        SH3ADD = auto()  # Logic left shift by 3 and add

        # ZBB extension
        ANDN = auto()  # Bitwise ANDN
        ORN = auto()  # Bitwise ORN
        XNOR = auto()  # Bitwise XNOR

        CLZ = auto()  # Count leading zeros
        CTZ = auto()  # Count trailing zeros
        CPOP = auto()  # Count set bits

        MAX = auto()  # Maximum
        MAXU = auto()  # Unsigned maximum
        MIN = auto()  # Minimum
        MINU = auto()  # Unsigned minimum

        SEXTB = auto()  # Sign-extend byte
        SEXTH = auto()  # Sign-extend halfword
        ZEXTH = auto()  # Zero extend halfword

        ORCB = auto()  # Bitwise or combine
        REV8 = auto()  # Reverse byte ordering

    def get_instructions(self) -> Sequence[tuple]:
        return (
            [
                (self.Fn.ADD, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
                (self.Fn.SUB, OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
                (self.Fn.SLT, OpType.COMPARE, Funct3.SLT),
                (self.Fn.SLTU, OpType.COMPARE, Funct3.SLTU),
                (self.Fn.XOR, OpType.LOGIC, Funct3.XOR),
                (self.Fn.OR, OpType.LOGIC, Funct3.OR),
                (self.Fn.AND, OpType.LOGIC, Funct3.AND),
            ]
            + [
                (self.Fn.SH1ADD, OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD),
                (self.Fn.SH2ADD, OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD),
                (self.Fn.SH3ADD, OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD),
            ]
            * self.zba_enable
            + [
                (self.Fn.ANDN, OpType.BIT_MANIPULATION, Funct3.ANDN, Funct7.ANDN),
                (self.Fn.XNOR, OpType.BIT_MANIPULATION, Funct3.XNOR, Funct7.XNOR),
                (self.Fn.ORN, OpType.BIT_MANIPULATION, Funct3.ORN, Funct7.ORN),
                (self.Fn.MAX, OpType.BIT_MANIPULATION, Funct3.MAX, Funct7.MAX),
                (self.Fn.MAXU, OpType.BIT_MANIPULATION, Funct3.MAXU, Funct7.MAX),
                (self.Fn.MIN, OpType.BIT_MANIPULATION, Funct3.MIN, Funct7.MIN),
                (self.Fn.MINU, OpType.BIT_MANIPULATION, Funct3.MINU, Funct7.MIN),
                (self.Fn.ORCB, OpType.UNARY_BIT_MANIPULATION_1, Funct3.ORCB, Funct7.ORCB),
                (self.Fn.REV8, OpType.UNARY_BIT_MANIPULATION_1, Funct3.REV8, Funct7.REV8),
                (self.Fn.SEXTB, OpType.UNARY_BIT_MANIPULATION_1, Funct3.SEXTB, Funct7.SEXTB),
                (self.Fn.ZEXTH, OpType.UNARY_BIT_MANIPULATION_1, Funct3.ZEXTH, Funct7.ZEXTH),
                (self.Fn.CPOP, OpType.UNARY_BIT_MANIPULATION_5, Funct3.CPOP, Funct7.CPOP),
                (self.Fn.SEXTH, OpType.UNARY_BIT_MANIPULATION_2, Funct3.SEXTH, Funct7.SEXTH),
                (self.Fn.CLZ, OpType.UNARY_BIT_MANIPULATION_3, Funct3.CLZ, Funct7.CLZ),
                (self.Fn.CTZ, OpType.UNARY_BIT_MANIPULATION_4, Funct3.CTZ, Funct7.CTZ),
            ]
            * self.zbb_enable
        )


class CLZSubmodule(Elaboratable):
    def __init__(self, gen_params: GenParams):
        xlen = gen_params.isa.xlen
        self.in_sig = Signal(xlen)
        self.out_sig = Signal(xlen)

    def elaborate(self, platform) -> HasElaborate:
        m = Module()
        m.d.comb += self.out_sig.eq(count_leading_zeros(self.in_sig))
        return m


class Alu(Elaboratable):
    def __init__(self, gen_params: GenParams, alu_fn=AluFn()):
        self.zba_enable = alu_fn.zba_enable
        self.zbb_enable = alu_fn.zbb_enable
        self.gen_params = gen_params

        self.fn = alu_fn.get_function()
        self.in1 = Signal(gen_params.isa.xlen)
        self.in2 = Signal(gen_params.isa.xlen)

        self.out = Signal(gen_params.isa.xlen)

    def elaborate(self, platform):
        m = TModule()

        xlen = self.gen_params.isa.xlen

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(AluFn.Fn.ADD):
                m.d.comb += self.out.eq(self.in1 + self.in2)
            with OneHotCase(AluFn.Fn.XOR):
                m.d.comb += self.out.eq(self.in1 ^ self.in2)
            with OneHotCase(AluFn.Fn.OR):
                m.d.comb += self.out.eq(self.in1 | self.in2)
            with OneHotCase(AluFn.Fn.AND):
                m.d.comb += self.out.eq(self.in1 & self.in2)
            with OneHotCase(AluFn.Fn.SUB):
                m.d.comb += self.out.eq(self.in1 - self.in2)
            with OneHotCase(AluFn.Fn.SLT):
                m.d.comb += self.out.eq(self.in1.as_signed() < self.in2.as_signed())
            with OneHotCase(AluFn.Fn.SLTU):
                m.d.comb += self.out.eq(self.in1 < self.in2)

            if self.zba_enable:
                with OneHotCase(AluFn.Fn.SH1ADD):
                    m.d.comb += self.out.eq((self.in1 << 1) + self.in2)
                with OneHotCase(AluFn.Fn.SH2ADD):
                    m.d.comb += self.out.eq((self.in1 << 2) + self.in2)
                with OneHotCase(AluFn.Fn.SH3ADD):
                    m.d.comb += self.out.eq((self.in1 << 3) + self.in2)

            if self.zbb_enable:
                m.submodules.clz = clz = CLZSubmodule(self.gen_params)

                with OneHotCase(AluFn.Fn.ANDN):
                    m.d.comb += self.out.eq(self.in1 & ~self.in2)
                with OneHotCase(AluFn.Fn.XNOR):
                    m.d.comb += self.out.eq(~(self.in1 ^ self.in2))
                with OneHotCase(AluFn.Fn.ORN):
                    m.d.comb += self.out.eq(self.in1 | ~self.in2)
                with OneHotCase(AluFn.Fn.MIN):
                    with m.If(self.in1.as_signed() < self.in2.as_signed()):
                        m.d.comb += self.out.eq(self.in1)
                    with m.Else():
                        m.d.comb += self.out.eq(self.in2)
                with OneHotCase(AluFn.Fn.MINU):
                    with m.If(self.in1 < self.in2):
                        m.d.comb += self.out.eq(self.in1)
                    with m.Else():
                        m.d.comb += self.out.eq(self.in2)
                with OneHotCase(AluFn.Fn.MAX):
                    with m.If(self.in1.as_signed() >= self.in2.as_signed()):
                        m.d.comb += self.out.eq(self.in1)
                    with m.Else():
                        m.d.comb += self.out.eq(self.in2)
                with OneHotCase(AluFn.Fn.MAXU):
                    with m.If(self.in1 >= self.in2):
                        m.d.comb += self.out.eq(self.in1)
                    with m.Else():
                        m.d.comb += self.out.eq(self.in2)
                with OneHotCase(AluFn.Fn.CPOP):
                    m.d.comb += self.out.eq(popcount(self.in1))
                with OneHotCase(AluFn.Fn.CLZ):
                    m.d.comb += clz.in_sig.eq(self.in1)
                    m.d.comb += self.out.eq(clz.out_sig)
                with OneHotCase(AluFn.Fn.CTZ):
                    m.d.comb += clz.in_sig.eq(self.in1[::-1])
                    m.d.comb += self.out.eq(clz.out_sig)
                with OneHotCase(AluFn.Fn.SEXTH):
                    m.d.comb += self.out.eq(Cat(self.in1[0:16], Repl(self.in1[15], xlen - 16)))
                with OneHotCase(AluFn.Fn.SEXTB):
                    m.d.comb += self.out.eq(Cat(self.in1[0:8], Repl(self.in1[7], xlen - 8)))
                with OneHotCase(AluFn.Fn.ZEXTH):
                    m.d.comb += self.out.eq(Cat(self.in1[0:16], C(0, shape=unsigned(xlen - 16))))
                with OneHotCase(AluFn.Fn.ORCB):

                    def _or(s: Value) -> Value:
                        return Repl(s.any(), 8)

                    for i in range(xlen // 8):
                        m.d.comb += self.out[i * 8 : (i + 1) * 8].eq(_or(self.in1[i * 8 : (i + 1) * 8]))
                with OneHotCase(AluFn.Fn.REV8):
                    en = xlen // 8
                    for i in range(en):
                        j = en - i - 1
                        m.d.comb += self.out[i * 8 : (i + 1) * 8].eq(self.in1[j * 8 : (j + 1) * 8])
        return m


class AluFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, alu_fn=AluFn()):
        self.gen_params = gen_params
        self.alu_fn = alu_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.clear = Method()

    def elaborate(self, platform):
        m = TModule()

        m.submodules.alu = alu = Alu(self.gen_params, alu_fn=self.alu_fn)
        m.submodules.fifo = fifo = BasicFifo(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.alu_fn.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.comb += alu.fn.eq(decoder.decode_fn)

            m.d.comb += alu.in1.eq(arg.s1_val)
            m.d.comb += alu.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            fifo.write(m, rob_id=arg.rob_id, result=alu.out, rp_dst=arg.rp_dst, exception=0)

        self.clear.proxy(m, fifo.clear)
        self.clear.add_conflict(self.issue, priority=Priority.LEFT)
        self.clear.add_conflict(self.accept, priority=Priority.LEFT)

        return m


class ALUComponent(FunctionalComponentParams):
    def __init__(self, zba_enable=False, zbb_enable=False):
        self.zba_enable = zba_enable
        self.zbb_enable = zbb_enable
        self.alu_fn = AluFn(zba_enable=zba_enable, zbb_enable=zbb_enable)

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return AluFuncUnit(gen_params, self.alu_fn)

    def get_optypes(self) -> set[OpType]:
        return self.alu_fn.get_op_types()
