from typing import Sequence, Type
from amaranth import *

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.utils import OneHotSwitch

from coreblocks.fu.fu_decoder import DecoderManager

__all__ = ["AluFuncUnit", "ALUComponent"]

from coreblocks.utils.protocols import FuncUnit

class Alu(Elaboratable):
    def __init__(self, gen: GenParams, fn):
        self.gen = gen

        self.fn = Signal(fn)
        self.enum = fn
        self.in1 = Signal(gen.isa.xlen)
        self.in2 = Signal(gen.isa.xlen)

        self.out = Signal(gen.isa.xlen)

    def elaborate(self, platform):
        m = Module()

        xlen = self.gen.isa.xlen
        xlen_log = self.gen.isa.xlen_log

        with OneHotSwitch(m, self.fn) as OneHotCase:
            if hasattr(self.enum, "ADD"):
                with OneHotCase(self.enum["ADD"]):
                    m.d.comb += self.out.eq(self.in1 + self.in2)
            if hasattr(self.enum, "SLL"):
                with OneHotCase(self.enum["SLL"]):
                    m.d.comb += self.out.eq(self.in1 << self.in2[0:xlen_log])
            if hasattr(self.enum, "XOR"):
                with OneHotCase(self.enum["XOR"]):
                    m.d.comb += self.out.eq(self.in1 ^ self.in2)
            if hasattr(self.enum, "SRL"):
                with OneHotCase(self.enum["SRL"]):
                    m.d.comb += self.out.eq(self.in1 >> self.in2[0:xlen_log])
            if hasattr(self.enum, "OR"):    
                with OneHotCase(self.enum["OR"]):
                    m.d.comb += self.out.eq(self.in1 | self.in2)
            if hasattr(self.enum, "AND"):
                with OneHotCase(self.enum["AND"]):
                    m.d.comb += self.out.eq(self.in1 & self.in2)
            if hasattr(self.enum, "SUB"):
                with OneHotCase(self.enum["SUB"]):
                    m.d.comb += self.out.eq(self.in1 - self.in2)
            if hasattr(self.enum, "SRA"):
                with OneHotCase(self.enum["SRA"]):
                    m.d.comb += self.out.eq(Cat(self.in1, Repl(self.in1[xlen - 1], xlen)) >> self.in2[0:xlen_log])
            if hasattr(self.enum, "SLT"):
                with OneHotCase(self.enum["SLT"]):
                    m.d.comb += self.out.eq(self.in1.as_signed() < self.in2.as_signed())
            if hasattr(self.enum, "SLTU"):
                with OneHotCase(self.enum["SLTU"]):
                    m.d.comb += self.out.eq(self.in1 < self.in2)
            if hasattr(self.enum, "SH1ADD"):
                with OneHotCase(self.enum["SH1ADD"]):
                    m.d.comb += self.out.eq((self.in1 << 1) + self.in2)
            if hasattr(self.enum, "SH2ADD"):
                with OneHotCase(self.enum["SH2ADD"]):
                    m.d.comb += self.out.eq((self.in1 << 2) + self.in2)
            if hasattr(self.enum, "SH3ADD"):
                with OneHotCase(self.enum["SH3ADD"]):
                    m.d.comb += self.out.eq((self.in1 << 3) + self.in2)
                    

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return m


class AluFuncUnit(Elaboratable):
    def __init__(self, gen: GenParams, alu_fn: Type[DecoderManager]):
        self.gen = gen
        self.alu_fn = alu_fn
        self.optypes = alu_fn.get_op_types()

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.alu = alu = Alu(self.gen, self.alu_fn.Fn)
        m.submodules.fifo = fifo = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.alu_fn.get_decoder(self.gen)

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
    def __init__(self, decoder_manager: Type[DecoderManager]):
        self.decoder_manager = decoder_manager

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return AluFuncUnit(gen_params, self.decoder_manager)

    def get_optypes(self) -> set[OpType]:
        return self.decoder_manager.get_op_types()