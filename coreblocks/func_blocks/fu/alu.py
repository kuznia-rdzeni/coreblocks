from dataclasses import dataclass, KW_ONLY, field
from typing import Sequence
from amaranth import *

from transactron import *
from transactron.lib import FIFO
from transactron.lib.metrics import *

from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.params import GenParams, FunctionalComponentParams
from transactron.utils import HasElaborate, OneHotSwitch

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.func_blocks.interface.func_protocols import FuncUnit

from transactron.utils import popcount, count_leading_zeros

__all__ = ["AluFuncUnit", "ALUComponent"]


class AluFn(DecoderManager):
    def __init__(self, zba_enable=False, zbb_enable=False, zicond_enable=False) -> None:
        self.zba_enable = zba_enable
        self.zbb_enable = zbb_enable
        self.zicond_enable = zicond_enable

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

        # ZICOND extension
        CZEROEQZ = auto()  # Move zero if condition if equal to zero
        CZERONEZ = auto()  # Move zero if condition is nonzero

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
                (self.Fn.REV8, OpType.UNARY_BIT_MANIPULATION_1, Funct3.REV8),
                (self.Fn.SEXTB, OpType.UNARY_BIT_MANIPULATION_1, Funct3.SEXTB),
                (self.Fn.ZEXTH, OpType.UNARY_BIT_MANIPULATION_1, Funct3.ZEXTH),
                (self.Fn.ORCB, OpType.UNARY_BIT_MANIPULATION_2, Funct3.ORCB),
                (self.Fn.SEXTH, OpType.UNARY_BIT_MANIPULATION_2, Funct3.SEXTH),
                (self.Fn.CLZ, OpType.UNARY_BIT_MANIPULATION_3, Funct3.CLZ),
                (self.Fn.CTZ, OpType.UNARY_BIT_MANIPULATION_4, Funct3.CTZ),
                (self.Fn.CPOP, OpType.UNARY_BIT_MANIPULATION_5, Funct3.CPOP),
            ]
            * self.zbb_enable
            + [
                (self.Fn.CZEROEQZ, OpType.CZERO, Funct3.CZEROEQZ),
                (self.Fn.CZERONEZ, OpType.CZERO, Funct3.CZERONEZ),
            ]
            * self.zicond_enable
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
        self.zicond_enable = alu_fn.zicond_enable
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
                    m.d.comb += self.out.eq(Cat(self.in1[0:16], self.in1[15].replicate(xlen - 16)))
                with OneHotCase(AluFn.Fn.SEXTB):
                    m.d.comb += self.out.eq(Cat(self.in1[0:8], self.in1[7].replicate(xlen - 8)))
                with OneHotCase(AluFn.Fn.ZEXTH):
                    m.d.comb += self.out.eq(Cat(self.in1[0:16], C(0, shape=unsigned(xlen - 16))))
                with OneHotCase(AluFn.Fn.ORCB):

                    def _or(s: Value) -> Value:
                        return s.any().replicate(8)

                    for i in range(xlen // 8):
                        m.d.comb += self.out[i * 8 : (i + 1) * 8].eq(_or(self.in1[i * 8 : (i + 1) * 8]))
                with OneHotCase(AluFn.Fn.REV8):
                    en = xlen // 8
                    for i in range(en):
                        j = en - i - 1
                        m.d.comb += self.out[i * 8 : (i + 1) * 8].eq(self.in1[j * 8 : (j + 1) * 8])

            if self.zicond_enable:
                czero_cases = [
                    (AluFn.Fn.CZERONEZ, lambda is_zero: self.in1 if is_zero else 0),
                    (AluFn.Fn.CZEROEQZ, lambda is_zero: 0 if is_zero else self.in1),
                ]
                for fn, output_fn in czero_cases:
                    with OneHotCase(fn):
                        with m.If(self.in2.any()):
                            m.d.comb += self.out.eq(output_fn(False))
                        with m.Else():
                            m.d.comb += self.out.eq(output_fn(True))

        return m


class AluFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, alu_fn=AluFn()):
        self.gen_params = gen_params
        self.alu_fn = alu_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.perf_instr = TaggedCounter(
            "backend.fu.alu.instr",
            "Counts of instructions executed by the jumpbranch unit",
            tags=AluFn.Fn,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_instr]

        m.submodules.alu = alu = Alu(self.gen_params, alu_fn=self.alu_fn)
        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.alu_fn.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.av_comb += alu.fn.eq(decoder.decode_fn)

            m.d.av_comb += alu.in1.eq(arg.s1_val)
            m.d.av_comb += alu.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            self.perf_instr.incr(m, decoder.decode_fn)

            fifo.write(m, rob_id=arg.rob_id, result=alu.out, rp_dst=arg.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class ALUComponent(FunctionalComponentParams):
    _: KW_ONLY
    zba_enable: bool = False
    zbb_enable: bool = False
    zicond_enable: bool = False
    decoder_manager: AluFn = field(init=False)

    def get_decoder_manager(self):
        return AluFn(zba_enable=self.zba_enable, zbb_enable=self.zbb_enable, zicond_enable=self.zicond_enable)

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return AluFuncUnit(gen_params, self.decoder_manager)
