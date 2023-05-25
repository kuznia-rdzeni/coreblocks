from typing import Sequence
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import FIFO

from coreblocks.params import OpType, Funct3, Funct7, GenParams, FuncUnitLayouts, FunctionalComponentParams
from coreblocks.utils import OneHotSwitch

from coreblocks.fu.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.utils.protocols import FuncUnit

__all__ = ["AluFuncUnit", "ALUComponent"]


class AluFn(DecoderManager):
    def __init__(self, zba_enable=False) -> None:
        self.zba_enable = zba_enable

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

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.ADD, OpType.ARITHMETIC, Funct3.ADD, Funct7.ADD),
            (self.Fn.SUB, OpType.ARITHMETIC, Funct3.ADD, Funct7.SUB),
            (self.Fn.SLT, OpType.COMPARE, Funct3.SLT),
            (self.Fn.SLTU, OpType.COMPARE, Funct3.SLTU),
            (self.Fn.XOR, OpType.LOGIC, Funct3.XOR),
            (self.Fn.OR, OpType.LOGIC, Funct3.OR),
            (self.Fn.AND, OpType.LOGIC, Funct3.AND),
        ] + [
            (self.Fn.SH1ADD, OpType.ADDRESS_GENERATION, Funct3.SH1ADD, Funct7.SH1ADD),
            (self.Fn.SH2ADD, OpType.ADDRESS_GENERATION, Funct3.SH2ADD, Funct7.SH2ADD),
            (self.Fn.SH3ADD, OpType.ADDRESS_GENERATION, Funct3.SH3ADD, Funct7.SH3ADD),
        ] * self.zba_enable


class Alu(Elaboratable):
    def __init__(self, gen_params: GenParams, alu_fn=AluFn()):
        self.zba_enable = alu_fn.zba_enable

        self.fn = alu_fn.get_function()
        self.in1 = Signal(gen_params.isa.xlen)
        self.in2 = Signal(gen_params.isa.xlen)

        self.out = Signal(gen_params.isa.xlen)

    def elaborate(self, platform):
        m = Module()

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

        return m


class AluFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, alu_fn=AluFn()):
        self.gen_params = gen_params
        self.alu_fn = alu_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.alu = alu = Alu(self.gen_params, alu_fn=self.alu_fn)
        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
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

            fifo.write(m, rob_id=arg.rob_id, result=alu.out, rp_dst=arg.rp_dst)

        return m


class ALUComponent(FunctionalComponentParams):
    def __init__(self, zba_enable=False):
        self.zba_enable = zba_enable
        self.alu_fn = AluFn(zba_enable=zba_enable)

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return AluFuncUnit(gen_params, self.alu_fn)

    def get_optypes(self) -> set[OpType]:
        return self.alu_fn.get_op_types()
