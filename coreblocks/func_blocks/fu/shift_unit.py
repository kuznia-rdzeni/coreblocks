from dataclasses import dataclass, KW_ONLY, field
from typing import Sequence
from amaranth import *

from transactron import *
from transactron.lib import FIFO

from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.interface.layouts import FuncUnitLayouts
from transactron.utils import OneHotSwitch

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from enum import IntFlag, auto

from coreblocks.func_blocks.interface.func_protocols import FuncUnit

__all__ = ["ShiftFuncUnit", "ShiftUnitComponent"]


class ShiftUnitFn(DecoderManager):
    def __init__(self, zbb_enable=False) -> None:
        self.zbb_enable = zbb_enable

    class Fn(IntFlag):
        SLL = auto()  # Logic left shift
        SRL = auto()  # Logic right shift
        SRA = auto()  # Arithmetic right shift

        # ZBB Extension
        ROR = auto()  # Rotate right
        ROL = auto()  # Rotate left

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.SLL, OpType.SHIFT, Funct3.SLL),
            (self.Fn.SRL, OpType.SHIFT, Funct3.SR, Funct7.SL),
            (self.Fn.SRA, OpType.SHIFT, Funct3.SR, Funct7.SA),
        ] + [
            (self.Fn.ROR, OpType.BIT_ROTATION, Funct3.ROR),
            (self.Fn.ROL, OpType.BIT_ROTATION, Funct3.ROL),
        ] * self.zbb_enable


class ShiftUnit(Elaboratable):
    def __init__(self, gen_params: GenParams, shift_unit_fn=ShiftUnitFn()):
        self.gen_params = gen_params
        self.zbb_enable = shift_unit_fn.zbb_enable

        self.fn = shift_unit_fn.get_function()
        self.in1 = Signal(gen_params.isa.xlen)
        self.in2 = Signal(gen_params.isa.xlen)

        self.out = Signal(gen_params.isa.xlen)

    def elaborate(self, platform):
        m = TModule()

        xlen = self.gen_params.isa.xlen
        xlen_log = self.gen_params.isa.xlen_log

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(ShiftUnitFn.Fn.SLL):
                m.d.comb += self.out.eq(self.in1 << self.in2[0:xlen_log])
            with OneHotCase(ShiftUnitFn.Fn.SRL):
                m.d.comb += self.out.eq(self.in1 >> self.in2[0:xlen_log])
            with OneHotCase(ShiftUnitFn.Fn.SRA):
                m.d.comb += self.out.eq(Cat(self.in1, self.in1[xlen - 1].replicate(xlen)) >> self.in2[0:xlen_log])

            if self.zbb_enable:
                with OneHotCase(ShiftUnitFn.Fn.ROL):
                    m.d.comb += self.out.eq((Cat(self.in1, self.in1) << self.in2[0:xlen_log])[xlen : (2 * xlen)])
                with OneHotCase(ShiftUnitFn.Fn.ROR):
                    m.d.comb += self.out.eq(Cat(self.in1, self.in1) >> self.in2[0:xlen_log])

        return m


class ShiftFuncUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, shift_unit_fn=ShiftUnitFn()):
        self.gen_params = gen_params
        self.shift_unit_fn = shift_unit_fn

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.shift_alu = shift_alu = ShiftUnit(self.gen_params, shift_unit_fn=self.shift_unit_fn)
        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = self.shift_unit_fn.get_decoder(self.gen_params)

        @def_method(m, self.accept)
        def _():
            return fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.av_comb += shift_alu.fn.eq(decoder.decode_fn)

            m.d.av_comb += shift_alu.in1.eq(arg.s1_val)
            m.d.av_comb += shift_alu.in2.eq(Mux(arg.imm, arg.imm, arg.s2_val))

            fifo.write(m, rob_id=arg.rob_id, result=shift_alu.out, rp_dst=arg.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class ShiftUnitComponent(FunctionalComponentParams):
    _: KW_ONLY
    zbb_enable: bool = False
    decoder_manager: ShiftUnitFn = field(init=False)

    def get_decoder_manager(self):
        return ShiftUnitFn(zbb_enable=self.zbb_enable)

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ShiftFuncUnit(gen_params, self.decoder_manager)
