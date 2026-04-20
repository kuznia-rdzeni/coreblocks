from dataclasses import dataclass, KW_ONLY
from enum import IntFlag, auto
from typing import Sequence

from amaranth import *

from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.func_blocks.fu.common import DecoderManager, FuncUnitBase
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.params import FunctionalComponentParams, GenParams
from transactron import TModule, def_method
from transactron.utils import OneHotSwitch


class ZbkxFn(DecoderManager):
    class Fn(IntFlag):
        XPERM4 = auto()
        XPERM8 = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.XPERM4, OpType.CROSSBAR_PERMUTATION, Funct3.XPERM4, Funct7.XPERM),
            (self.Fn.XPERM8, OpType.CROSSBAR_PERMUTATION, Funct3.XPERM8, Funct7.XPERM),
        ]


class Zbkx(Elaboratable):
    def __init__(self, gen_params: GenParams, fn=ZbkxFn()):
        self.gen_params = gen_params
        self.xlen = gen_params.isa.xlen

        self.fn = fn.get_function()
        self.in1 = Signal(self.xlen)
        self.in2 = Signal(self.xlen)
        self.result = Signal(self.xlen)

    def elaborate(self, platform):
        m = TModule()

        with OneHotSwitch(m, self.fn) as OneHotCase:
            with OneHotCase(ZbkxFn.Fn.XPERM4):
                lane_count = self.xlen // 4
                for lane in range(lane_count):
                    idx = self.in2.word_select(lane, 4)
                    selected = Mux(idx < lane_count, self.in1.word_select(idx, 4), C(0, 4))
                    m.d.comb += self.result.word_select(lane, 4).eq(selected)

            with OneHotCase(ZbkxFn.Fn.XPERM8):
                lane_count = self.xlen // 8
                for lane in range(lane_count):
                    idx = self.in2.word_select(lane, 8)
                    selected = Mux(idx < lane_count, self.in1.word_select(idx, 8), C(0, 8))
                    m.d.comb += self.result.word_select(lane, 8).eq(selected)

        return m


class ZbkxUnit(FuncUnitBase[ZbkxFn]):
    def __init__(self, gen_params: GenParams, fn=ZbkxFn()):
        super().__init__(gen_params, fn)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.zbkx = zbkx = Zbkx(self.gen_params, fn=self.fn)
        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)

        @def_method(m, self.issue)
        def _(arg):
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)

            m.d.av_comb += zbkx.fn.eq(decoder.decode_fn)
            m.d.av_comb += zbkx.in1.eq(arg.s1_val)
            m.d.av_comb += zbkx.in2.eq(arg.s2_val)

            self.push_result(m, rob_id=arg.rob_id, result=zbkx.result, rp_dst=arg.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class ZbkxComponent(FunctionalComponentParams):
    _: KW_ONLY
    decoder_manager: ZbkxFn = ZbkxFn()
    result_fifo: bool = True

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbkxUnit(gen_params, self.decoder_manager)
