from dataclasses import KW_ONLY, dataclass
from enum import IntFlag, auto
from collections.abc import Sequence

from amaranth import *
from amaranth.lib import data

from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.params import GenParams
from coreblocks.arch import OpType, Funct3
from coreblocks.interface.layouts import FuncUnitLayouts
from transactron import *
from transactron.core import def_method
from transactron.lib import *

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager

from transactron.utils import OneHotSwitch
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.func_blocks.fu.division.long_division import LongDivider


class DivFn(DecoderManager):
    class Fn(IntFlag):
        DIV = auto()
        DIVU = auto()
        REM = auto()
        REMU = auto()

    def get_instructions(self) -> Sequence[tuple]:
        return [
            (self.Fn.DIV, OpType.DIV_REM, Funct3.DIV),
            (self.Fn.DIVU, OpType.DIV_REM, Funct3.DIVU),
            (self.Fn.REM, OpType.DIV_REM, Funct3.REM),
            (self.Fn.REMU, OpType.DIV_REM, Funct3.REMU),
        ]


def get_input(arg: data.View) -> tuple[Value, Value]:
    return arg.s1_val, Mux(arg.imm, arg.imm, arg.s2_val)


class DivUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, ipc: int = 4, div_fn=DivFn()):
        self.gen_params = gen_params
        self.ipc = ipc

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.clear = Method()

        self.div_fn = div_fn

    def elaborate(self, platform):
        m = TModule()

        m.submodules.result_fifo = result_fifo = BasicFifo(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.params_fifo = params_fifo = FIFO(
            [
                ("rob_id", self.gen_params.rob_entries_bits),
                ("rp_dst", self.gen_params.phys_regs_bits),
                ("flip_sign", 1),
                ("rem_res", 1),
            ],
            2,
        )
        m.submodules.decoder = decoder = self.div_fn.get_decoder(self.gen_params)

        m.submodules.divider = divider = LongDivider(self.gen_params, self.ipc)

        xlen = self.gen_params.isa.xlen
        sign_bit = xlen - 1  # position of sign bit

        @def_method(m, self.clear)
        def _():
            result_fifo.clear(m)
            divider.clear(m)

        @def_method(m, self.accept)
        def _():
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)
            i1, i2 = get_input(arg)

            flip_sign = Signal(1)  # if result is negative number
            rem_res = Signal(1)  # flag whether we want quotient or remainder

            dividend = Signal(xlen)
            divisor = Signal(xlen)

            def _abs(s: Value) -> Value:
                return Mux(s.as_signed() < 0, -s, s)

            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(DivFn.Fn.DIVU):
                    m.d.av_comb += flip_sign.eq(0)
                    m.d.av_comb += rem_res.eq(0)
                    m.d.av_comb += dividend.eq(i1)
                    m.d.av_comb += divisor.eq(i2)
                with OneHotCase(DivFn.Fn.DIV):
                    # quotient is negative if divisor and dividend have different signs
                    m.d.av_comb += flip_sign.eq(i1[sign_bit] ^ i2[sign_bit])
                    m.d.av_comb += rem_res.eq(0)
                    m.d.av_comb += dividend.eq(_abs(i1))
                    m.d.av_comb += divisor.eq(_abs(i2))
                with OneHotCase(DivFn.Fn.REMU):
                    m.d.av_comb += flip_sign.eq(0)
                    m.d.av_comb += rem_res.eq(1)
                    m.d.av_comb += dividend.eq(i1)
                    m.d.av_comb += divisor.eq(i2)
                with OneHotCase(DivFn.Fn.REM):
                    # sign of remainder is equal to sign of dividend
                    m.d.av_comb += flip_sign.eq(i1[sign_bit])
                    m.d.av_comb += rem_res.eq(1)
                    m.d.av_comb += dividend.eq(_abs(i1))
                    m.d.av_comb += divisor.eq(_abs(i2))

            params_fifo.write(m, rob_id=arg.rob_id, rp_dst=arg.rp_dst, flip_sign=flip_sign, rem_res=rem_res)

            divider.issue(m, dividend=dividend, divisor=divisor)

        with Transaction().body(m):
            response = divider.accept(m)
            params = params_fifo.read(m)
            result = Mux(params.rem_res, response.remainder, response.quotient)
            # change sign but only if it was requested and sign is not correct
            flip_sig = Mux(params.flip_sign, ~result[sign_bit], 0)
            sign_result = Mux(flip_sig, -result, result)

            result_fifo.write(m, rob_id=params.rob_id, result=sign_result, rp_dst=params.rp_dst, exception=0)

        return m


@dataclass(frozen=True)
class DivComponent(FunctionalComponentParams):
    _: KW_ONLY
    ipc: int = 3  # iterations per cycle
    decoder_manager: DivFn = DivFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return DivUnit(gen_params, self.ipc, self.decoder_manager)
