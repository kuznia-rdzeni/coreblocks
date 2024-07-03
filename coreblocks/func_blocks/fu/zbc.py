from dataclasses import dataclass
from enum import IntFlag, auto, unique
from typing import Sequence

from amaranth import *

from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager
from coreblocks.params import GenParams, FunctionalComponentParams
from coreblocks.arch import OpType, Funct3
from coreblocks.interface.layouts import FuncUnitLayouts
from transactron import Method, def_method, TModule
from transactron.lib import FIFO
from transactron.utils import OneHotSwitch
from coreblocks.func_blocks.interface.func_protocols import FuncUnit


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


class ClMultiplier(Elaboratable):
    """
    Module for computing carry-less product

    Attributes
    ----------
    i1: Signal(unsigned(n)), in
        First factor.
    i2: Signal(unsigned(n)), in
        Second factor.
    result: Signal(unsigned(n * 2)), out
        Result.
    reset: Signal(1), in
        Setting this signal to 1 will start a new computation with provided inputs
    busy: Signal(1), out
        Set to 1 while a computation is in progress
    """

    def __init__(self, bit_width: int, recursion_depth: int):
        """
        Parameters
        ----------
        bit_width: int
            Bit width of inputs
        recursion_depth: int
            Depth of recursive submodules for parallel computation (assumes bit_width to be a power of 2)
        """
        if bit_width.bit_count() != 1:
            raise ValueError("bit_width should be a power of 2")
        if bit_width.bit_length() <= recursion_depth:
            raise ValueError("Too large recursion depth")

        self.recursion_depth = recursion_depth
        self.bit_width = bit_width

        self.i1 = Signal(unsigned(bit_width))
        self.i2 = Signal(unsigned(bit_width))
        self.result = Signal(unsigned(bit_width * 2))
        self.reset = Signal()
        self.busy = Signal()

    def elaborate(self, platform):
        if self.recursion_depth == 0:
            return self.iterative_module()
        else:
            return self.recursive_module()

    def iterative_module(self):
        m = Module()

        m.d.sync += self.busy.eq(0)

        v1 = Signal(unsigned(self.bit_width * 2))
        v2 = Signal(unsigned(self.bit_width))
        with m.If(self.reset):
            m.d.sync += self.result.eq(0)
            m.d.sync += [
                v1.eq(self.i1),
                v2.eq(self.i2),
            ]
            m.d.sync += self.busy.eq(1)

        with m.Elif(v2.bool()):
            with m.If(v2[0]):
                m.d.sync += self.result.eq(self.result ^ v1)
            m.d.sync += [
                v1.eq(v1 << 1),
                v2.eq(v2 >> 1),
            ]
            m.d.sync += self.busy.eq(1)

        return m

    def recursive_module(self):
        m = Module()

        half_width = self.bit_width // 2

        m.submodules.mul_ll = mul_ll = ClMultiplier(half_width, self.recursion_depth - 1)
        m.submodules.mul_lu = mul_lu = ClMultiplier(half_width, self.recursion_depth - 1)
        m.submodules.mul_ul = mul_ul = ClMultiplier(half_width, self.recursion_depth - 1)
        m.submodules.mul_uu = mul_uu = ClMultiplier(half_width, self.recursion_depth - 1)

        m.d.comb += [
            mul_ll.reset.eq(self.reset),
            mul_ul.reset.eq(self.reset),
            mul_lu.reset.eq(self.reset),
            mul_uu.reset.eq(self.reset),
        ]

        m.d.comb += self.busy.eq(mul_ll.busy | mul_lu.busy | mul_ul.busy | mul_uu.busy)

        m.d.comb += [
            mul_ll.i1.eq(self.i1[:half_width]),
            mul_ll.i2.eq(self.i2[:half_width]),
        ]
        m.d.comb += [
            mul_lu.i1.eq(self.i1[half_width:]),
            mul_lu.i2.eq(self.i2[:half_width]),
        ]
        m.d.comb += [
            mul_ul.i1.eq(self.i1[:half_width]),
            mul_ul.i2.eq(self.i2[half_width:]),
        ]
        m.d.comb += [
            mul_uu.i1.eq(self.i1[half_width:]),
            mul_uu.i2.eq(self.i2[half_width:]),
        ]

        m.d.comb += self.result.eq(
            (mul_uu.result << self.bit_width)
            ^ (mul_ul.result << half_width)
            ^ (mul_lu.result << half_width)
            ^ mul_ll.result
        )

        return m


class ZbcUnit(Elaboratable):
    """
    Module responsible for executing Zbc instructions (carry-less multiplication)

    Attributes
    ----------
    issue: Method(i=FuncUnitLayouts.issue)
        Method used for requesting computation.
    accept: Method(i=FuncUnitLayouts.accept)
        Method used for getting result of requested computation.
    """

    def __init__(self, gen_params: GenParams, recursion_depth: int, zbc_fn: ZbcFn):
        layouts = gen_params.get(FuncUnitLayouts)

        self.zbc_fn = zbc_fn
        self.recursion_depth = recursion_depth
        self.gen_params = gen_params
        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.params_fifo = params_fifo = FIFO(
            [
                ("rob_id", self.gen_params.rob_entries_bits),
                ("rp_dst", self.gen_params.phys_regs_bits),
                ("high_res", 1),
                ("rev_res", 1),
            ],
            1,
        )
        m.submodules.decoder = decoder = self.zbc_fn.get_decoder(self.gen_params)
        m.submodules.clmul = clmul = ClMultiplier(self.gen_params.isa.xlen, self.recursion_depth)

        m.d.comb += clmul.reset.eq(0)

        @def_method(m, self.accept, ready=~clmul.busy)
        def _():
            xlen = self.gen_params.isa.xlen

            output = clmul.result
            params = params_fifo.read(m)

            result = Mux(params.high_res, output[xlen:], output[:xlen])
            reversed_result = Mux(params.rev_res, result[::-1], result)

            return {"rob_id": params.rob_id, "rp_dst": params.rp_dst, "result": reversed_result, "exception": 0}

        @def_method(m, self.issue)
        def _(exec_fn, imm, s1_val, s2_val, rob_id, rp_dst, pc, ftq_addr):
            m.d.comb += decoder.exec_fn.eq(exec_fn)

            i1 = s1_val
            i2 = Mux(imm, imm, s2_val)

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
                    # clmulr is equivalent to bit-reversing the inputs,
                    # performing a clmul,
                    # then bit-reversing the output.
                    m.d.comb += high_res.eq(0)
                    m.d.comb += rev_res.eq(1)
                    m.d.comb += value1.eq(i1[::-1])
                    m.d.comb += value2.eq(i2[::-1])

            params_fifo.write(m, rob_id=rob_id, rp_dst=rp_dst, high_res=high_res, rev_res=rev_res)

            m.d.comb += clmul.i1.eq(value1)
            m.d.comb += clmul.i2.eq(value2)
            m.d.comb += clmul.reset.eq(1)

        return m


@dataclass(frozen=True)
class ZbcComponent(FunctionalComponentParams):
    recursion_depth: int = 3
    zbc_fn = ZbcFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return ZbcUnit(gen_params, self.recursion_depth, self.zbc_fn)

    def get_optypes(self) -> set[OpType]:
        return self.zbc_fn.get_op_types()
