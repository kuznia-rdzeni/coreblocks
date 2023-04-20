from enum import IntFlag, auto, unique
from typing import Sequence

from amaranth import *

from coreblocks.fu.fu_decoder import DecoderManager
from coreblocks.params import (
    Funct3,
    OpType,
    GenParams,
    FuncUnitLayouts,
    UnsignedMulUnitLayouts,
    FunctionalComponentParams,
)
from coreblocks.transactions import Method, def_method, Transaction
from coreblocks.transactions.lib import FIFO
from coreblocks.utils import OneHotSwitch
from coreblocks.utils.protocols import FuncUnit


class ZbcFn(DecoderManager):
    @unique
    class Fn(IntFlag):
        CLMUL = auto()
        CLMULH = auto()
        CLMULR = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
            (cls.Fn.CLMUL, OpType.CLMUL, Funct3.CLMUL),
            (cls.Fn.CLMULH, OpType.CLMUL, Funct3.CLMULH),
            (cls.Fn.CLMULR, OpType.CLMUL, Funct3.CLMULR),
        ]


class Zbc(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layout = gen_params.get(UnsignedMulUnitLayouts)

        self.issue = Method(i=layout.issue)
        self.accept = Method(o=layout.accept)

    def elaborate(self, platform):
        m = Module()
        output = Signal(unsigned(self.gen_params.isa.xlen * 2))

        i1 = Signal(unsigned(self.gen_params.isa.xlen * 2))
        i2 = Signal(unsigned(self.gen_params.isa.xlen))
        busy = Signal()

        @def_method(m, self.issue, ready=~busy)
        def _(arg):
            m.d.sync += output.eq(0)
            m.d.sync += i1.eq(arg.i1)
            m.d.sync += i2.eq(arg.i2)
            m.d.sync += busy.eq(1)

        @def_method(m, self.accept, ready=~i2.bool() & busy)
        def _():
            m.d.sync += busy.eq(0)
            return {"o": output}

        with m.If(busy):
            with m.If(i2[0]):
                m.d.sync += output.eq(output ^ i1)
            m.d.sync += i1.eq(i1 << 1)
            m.d.sync += i2.eq(i2 >> 1)

        return m


class ZbcUnit(Elaboratable):
    """
    Module responsible for executing carry-less multiplication (Zbc extension)

    Attributes
    ----------
    issue: Method(i=FuncUnitLayouts.issue)
        Method used for requesting computation.
    accept: Method(i=FuncUnitLayouts.accept)
        Method used for getting result of requested computation.
    """

    optypes = ZbcFn.get_op_types()

    def __init__(self, gen_params: GenParams):
        layouts = gen_params.get(FuncUnitLayouts)

        self.gen_params = gen_params
        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.params_fifo = params_fifo = FIFO(
            [
                ("rob_id", self.gen_params.rob_entries_bits),
                ("rp_dst", self.gen_params.phys_regs_bits),
                ("high_res", 1),
                ("rev_res", 1),
            ],
            2,
        )
        m.submodules.result_fifo = result_fifo = FIFO(self.gen_params.get(FuncUnitLayouts).accept, 2)
        m.submodules.decoder = decoder = ZbcFn.get_decoder(self.gen_params)
        m.submodules.zbc = zbc = Zbc(self.gen_params)

        @def_method(m, self.accept)
        def _():
            return result_fifo.read(m)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)

            i1 = arg.s1_val
            i2 = Mux(arg.imm, arg.imm, arg.s2_val)

            value1 = Signal(self.gen_params.isa.xlen)
            value2 = Signal(self.gen_params.isa.xlen)
            high_res = Signal(1)
            rev_res = Signal(1)

            with OneHotSwitch(m, decoder.decode_fn) as OneHotCase:
                with OneHotCase(ZbcFn.Fn.CLMUL):
                    m.d.comb += high_res.eq(0)
                    m.d.comb += rev_res.eq(0)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with OneHotCase(ZbcFn.Fn.CLMULH):
                    m.d.comb += high_res.eq(1)
                    m.d.comb += rev_res.eq(0)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with OneHotCase(ZbcFn.Fn.CLMULR):
                    # CLMULR is equivalent to bit-reversing the inputs,
                    # performing a clmul,
                    # then bit-reversing the output.
                    m.d.comb += high_res.eq(0)
                    m.d.comb += rev_res.eq(1)
                    m.d.comb += value1.eq(i1[::-1])
                    m.d.comb += value2.eq(i2[::-1])

            params_fifo.write(m, rob_id=arg.rob_id, rp_dst=arg.rp_dst, high_res=high_res, rev_res=rev_res)

            zbc.issue(m, i1=value1, i2=value2)

        xlen = self.gen_params.isa.xlen
        with Transaction().body(m):
            output = zbc.accept(m)
            params = params_fifo.read(m)

            result = Mux(params.high_res, output[xlen:], output[:xlen])
            reversed_result = Mux(params.rev_res, result[::-1], result)

            result_fifo.write(m, result=reversed_result, rob_id=params.rob_id, rp_dst=params.rp_dst)

        return m


class ZbcComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbcUnit(gen_params)

    def get_optypes(self) -> set[OpType]:
        return ZbcUnit.optypes
