from enum import IntEnum, unique
from typing import Tuple

from amaranth import *

from coreblocks.isa import OpType, Funct3
from coreblocks.mul_params import MulType, MulUnitParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.genparams import GenParams
from coreblocks.layouts import *
from coreblocks.unsigned_mul_unit import ShiftUnsignedMul, SequentialUnsignedMul, RecursiveUnsignedMul

__all__ = ["MulUnit", "MulFn"]

from coreblocks.utils import OneHotSwitch


class MulFn(Signal):
    """
    Hot wire enum of 5 different multiplication operations.
    """

    @unique
    class Fn(IntEnum):
        MUL = 1 << 0  # Lower part multiplication
        MULH = 1 << 1  # Upper part multiplication signed×signed
        MULHU = 1 << 2  # Upper part multiplication unsigned×unsigned
        MULHSU = 1 << 3  # Upper part multiplication signed×unsigned
        MULW = 1 << 4  # Multiplication of lower half of bits

    def __init__(self, *args, **kwargs):
        super().__init__(MulFn.Fn, *args, **kwargs)


class MulFnDecoder(Elaboratable):
    """
    Module decoding function into hot wired MulFn.
    """

    def __init__(self, gen: GenParams):
        layouts = gen.get(CommonLayouts)

        self.exec_fn = Record(layouts.exec_fn)
        self.mul_fn = MulFn()

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.exec_fn.funct3):
            with m.Case(Funct3.MUL):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MUL)
            with m.Case(Funct3.MULH):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MULH)
            with m.Case(Funct3.MULHU):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MULHU)
            with m.Case(Funct3.MULHSU):
                m.d.comb += self.mul_fn.eq(MulFn.Fn.MULHSU)

        with m.If(self.exec_fn.op_type == OpType.ARITHMETIC_W):
            m.d.comb += self.mul_fn.eq(MulFn.Fn.MULW)

        return m


def get_input(arg: Record) -> Tuple[Value, Value]:
    """
    Operation of getting two input values.

    Parameters
    ----------
    arg: Record
        Arguments of functional unit issue call.

    Returns
    -------
    return : Tuple[Value, Value]
        Two input values.
    """
    return arg.s1_val, Mux(arg.imm, arg.imm, arg.s2_val)


class MulUnit(Elaboratable):
    """
    Module responsible for handling every kind of multiplication based on selected unsigned integer multiplication
    module.
    """

    def __init__(self, gen: GenParams):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)

    def elaborate(self, platform):
        m = Module()

        m.submodules.result_fifo = result_fifo = FIFO(self.gen.get(FuncUnitLayouts).accept, 2)
        m.submodules.params_fifo = params_fifo = FIFO(
            [("rob_id", self.gen.rob_entries_bits), ("rp_dst", self.gen.phys_regs_bits)], 2
        )
        m.submodules.decoder = decoder = MulFnDecoder(self.gen)

        # Selecting unsigned integer multiplication module
        match self.gen.mul_unit_params:
            case MulUnitParams(mul_type=MulType.SHIFT_MUL):
                m.submodules.multiplier = multiplier = ShiftUnsignedMul(self.gen)
            case MulUnitParams(mul_type=MulType.SEQUENCE_MUL):
                m.submodules.multiplier = multiplier = SequentialUnsignedMul(self.gen)
            case MulUnitParams(mul_type=MulType.RECURSIVE_MUL):
                m.submodules.multiplier = multiplier = RecursiveUnsignedMul(self.gen)
            case _:
                raise Exception("None existing multiplication unit type")

        idle = Signal(1, reset=1)  # if unit is idle

        value1 = Signal(self.gen.isa.xlen)  # input value for multiplier submodule
        value2 = Signal(self.gen.isa.xlen)  # input value for multiplier submodule
        negative_res = Signal(1)  # if result is negative number
        high_res = Signal(1)  # if result should contain upper part of result

        xlen = self.gen.isa.xlen
        sign_bit = xlen - 1  # position of sign bit
        half_sign_bit = xlen // 2 - 1  # position of sign bit considering only half of input being used

        @def_method(m, self.accept)
        def _(arg):
            return result_fifo.read(m)

        @def_method(m, self.issue, ready=idle)
        def _(arg):
            params_fifo.write(m, {"rob_id": arg.rob_id, "rp_dst": arg.rp_dst})
            m.d.comb += decoder.exec_fn.eq(arg.exec_fn)
            i1, i2 = get_input(arg)

            with OneHotSwitch(m, decoder.mul_fn) as OneHotCase:
                with OneHotCase(MulFn.Fn.MUL):  # MUL
                    m.d.sync += negative_res.eq(0)
                    m.d.sync += high_res.eq(0)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with OneHotCase(MulFn.Fn.MULH):
                    m.d.sync += negative_res.eq(i1[sign_bit] ^ i2[sign_bit])
                    m.d.sync += high_res.eq(1)
                    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.comb += value2.eq(Mux(i2[sign_bit], -i2, i2))
                with OneHotCase(MulFn.Fn.MULHU):
                    m.d.sync += negative_res.eq(0)
                    m.d.sync += high_res.eq(1)
                    m.d.comb += value1.eq(i1)
                    m.d.comb += value2.eq(i2)
                with OneHotCase(MulFn.Fn.MULHSU):
                    m.d.sync += negative_res.eq(i1[sign_bit])
                    m.d.sync += high_res.eq(1)
                    m.d.comb += value1.eq(Mux(i1[sign_bit], -i1, i1))
                    m.d.comb += value2.eq(i2)
                with OneHotCase(MulFn.Fn.MULW):
                    m.d.sync += negative_res.eq(i1[half_sign_bit] ^ i2[half_sign_bit])
                    m.d.sync += high_res.eq(0)
                    i1h = Signal(xlen // 2)
                    i2h = Signal(xlen // 2)
                    m.d.comb += i1h.eq(Mux(i1[half_sign_bit], -i1, i1))
                    m.d.comb += i2h.eq(Mux(i2[half_sign_bit], -i2, i2))
                    m.d.comb += value1.eq(i1h)
                    m.d.comb += value2.eq(i2h)

            multiplier.issue(m, {"i1": value1, "i2": value2})
            m.d.sync += idle.eq(0)

        with Transaction().body(m):
            response = multiplier.accept(m)  # get result form unsigned multiplier
            sign_result = Mux(negative_res, -response.o, response.o)  # changing sign of result
            result = Mux(high_res, sign_result[xlen:], sign_result[:xlen])  # selecting upper or lower bits
            params = params_fifo.read(m)

            result_fifo.write(m, arg={"rob_id": params.rob_id, "result": result, "rp_dst": params.rp_dst})
            m.d.sync += idle.eq(1)

        return m
