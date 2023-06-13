from enum import IntFlag, auto
from typing import Sequence, Tuple

from amaranth import *

from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.params import Funct3, GenParams, FuncUnitLayouts, OpType
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.fu.fu_decoder import DecoderManager

from coreblocks.utils import OneHotSwitch
from coreblocks.utils.protocols import FuncUnit
from coreblocks.fu.divison.long_division import LongDivider


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


def get_input(arg: Record) -> Tuple[Value, Value]:
    return arg.s1_val, Mux(arg.imm, arg.imm, arg.s2_val)


class DivUnit(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, div_fn=DivFn()):
        self.gen_params = gen_params

        layouts = gen_params.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

        self.div_fn = div_fn

    def elaborate(self, platform):
        m = TModule()

        m.submodules.result_fifo = result_fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.params_fifo = params_fifo = FIFO(
            [
                ("rob_id", self.gen_params.rob_entries_bits),
                ("rp_dst", self.gen_params.phys_regs_bits),
                ("negative_res", 1),
                ("rem_res", 1),
            ],
            2,
        )
        m.submodules.decoder = decoder = self.div_fn.get_decoder(self.gen_params)

        m.submodules.divider = divider = LongDivider(self.gen_params)

        xlen = self.gen_params.isa.xlen
        # sign_bit = xlen - 1  # position of sign bit

        @def_method(m, self.accept)
        def _():
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            i1, i2 = get_input(arg)

            value1 = Signal(xlen)  # input value for multiplier submodule
            value2 = Signal(xlen)  # input value for multiplier submodule
            negative_res = Signal(1)  # if result is negative number
            rem_res = Signal(1)  # flag wheather we want result or reminder

            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(DivFn.Fn.DIV):
                    m.d.comb += negative_res.eq(0)
                    m.d.comb += rem_res.eq(0)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                # with OneHotCase(DivFn.Fn.DIVU):
                #    m.d.comb += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                #    m.d.comb += rem_res.eq(0)
                #    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                #    m.d.comb += value2.eq(Mux(i2[sign_bit], -i2, i2))
                with OneHotCase(DivFn.Fn.REM):
                    m.d.comb += negative_res.eq(0)
                    m.d.comb += rem_res.eq(1)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                # with OneHotCase(DivFn.Fn.REMU):
                #    m.d.comb += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                #    m.d.comb += rem_res.eq(1)
                #    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                #    m.d.comb += value2.eq(Mux(i2[sign_bit], -i2, i2))

            params_fifo.write(m, rob_id=arg.rob_id, rp_dst=arg.rp_dst, negative_res=negative_res, rem_res=rem_res)

            divider.issue(m, dividend=value1, divisor=value2)

        with Transaction().body(m):
            response = divider.accept(m)
            params = params_fifo.read(m)
            result = Mux(params.rem_res, response.reminder, response.quotient)
            # sign_result = Mux(params.negative_res, -result, result)  # changing sign of result
            # result = Mux(params.high_res, sign_result[xlen:], sign_result[:xlen])  # selecting upper or lower bits

            result_fifo.write(m, rob_id=params.rob_id, result=result, rp_dst=params.rp_dst)

        return m


class DivComponent(FunctionalComponentParams):
    def __init__(self) -> None:
        self.div_fn = DivFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return DivUnit(gen_params, self.div_fn)

    def get_optypes(self) -> set[OpType]:
        return self.div_fn.get_op_types()
