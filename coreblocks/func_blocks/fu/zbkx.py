from dataclasses import dataclass, KW_ONLY
from enum import IntFlag, auto
from typing import Sequence

from amaranth import *

from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.params import FunctionalComponentParams, GenParams
from transactron import Method, TModule, def_method
from transactron.utils import OneHotSwitch


class ZbkxFunction(DecoderManager):
    class Fn(IntFlag):
        XPERM4 = auto()
        XPERM8 = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.XPERM4, OpType.CROSSBAR_PERMUTATION, Funct3.XPERM4, Funct7.XPERM),
            (self.Fn.XPERM8, OpType.CROSSBAR_PERMUTATION, Funct3.XPERM8, Funct7.XPERM),
        ]


class Zbkx(Elaboratable):
    def __init__(self, gen_params: GenParams, function=ZbkxFunction()):
        self.gen_params = gen_params
        self.xlen = gen_params.isa.xlen

        self.function = function.get_function()
        self.in1 = Signal(self.xlen)
        self.in2 = Signal(self.xlen)
        self.result = Signal(self.xlen)

    def elaborate(self, platform):
        m = TModule()

        with OneHotSwitch(m, self.function) as OneHotCase:
            with OneHotCase(ZbkxFunction.Fn.XPERM4):
                lane_count = self.xlen // 4
                for lane in range(lane_count):
                    idx = self.in2.word_select(lane, 4)
                    selected = Mux(idx < lane_count, self.in1.word_select(idx, 4), C(0, 4))
                    m.d.comb += self.result.word_select(lane, 4).eq(selected)

            with OneHotCase(ZbkxFunction.Fn.XPERM8):
                lane_count = self.xlen // 8
                for lane in range(lane_count):
                    idx = self.in2.word_select(lane, 8)
                    selected = Mux(idx < lane_count, self.in1.word_select(idx, 8), C(0, 8))
                    m.d.comb += self.result.word_select(lane, 8).eq(selected)

        return m


class ZbkxUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, zbkx_fn=ZbkxFunction()):
        layouts = gen_params.get(FuncUnitLayouts)

        self.gen_params = gen_params
        self.issue = Method(i=layouts.issue)
        self.push_result = Method(i=layouts.push_result)

        self.zbkx_fn = zbkx_fn

    def elaborate(self, platform):
        m = TModule()

        m.submodules.zbkx = zbkx = Zbkx(self.gen_params, function=self.zbkx_fn)
        m.submodules.decoder = decoder = self.zbkx_fn.get_decoder(self.gen_params)

        @def_method(m, self.issue)
        def _(arg):
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)

            m.d.av_comb += zbkx.function.eq(decoder.decode_fn)
            m.d.av_comb += zbkx.in1.eq(arg.s1_val)
            m.d.av_comb += zbkx.in2.eq(arg.s2_val)

            self.push_result(m, rob_id=arg.rob_id, result=zbkx.result, rp_dst=arg.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class ZbkxComponent(FunctionalComponentParams):
    _: KW_ONLY
    decoder_manager: ZbkxFunction = ZbkxFunction()
    result_fifo: bool = True

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbkxUnit(gen_params, self.decoder_manager)
