from amaranth import *

from coreblocks.layouts import UnsignedMulUnitLayouts
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method

from coreblocks.genparams import GenParams

__all__ = ["MulBaseUnsigned", "ShiftUnsignedMul", "SequentialUnsignedMul", "RecursiveUnsignedMul"]


class MulBaseUnsigned(Elaboratable):
    """
    Abstract module creating common interface of unsigned multiplication module
    """

    def __init__(self, gen: GenParams):
        self.gen = gen

        layout = gen.get(UnsignedMulUnitLayouts)

        self.issue = Method(i=layout.issue)
        self.accept = Method(o=layout.accept)


class DSPMulUnit(Elaboratable):
    """
    Module for 1 clock cycle multiplication, designed to be replaced by DSP be HDL compiler

    Parameters
    ----------
    dsp_width: int
        width on multiplied numbers
    """

    def __init__(self, dsp_width: int):
        self.n = n = dsp_width

        self.compute = Method(i=[("i1", n), ("i2", n)], o=[("o", 2 * n)])

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.compute)
        def _(arg):
            # Here will be connection to DSP but right now I have no idea how to do it
            return {"o": arg.i1 * arg.i2}

        return m


class RecursiveWithSingleDSPMul(Elaboratable):
    """
    Module with combinatorial connection for sequential multiplication using single DSP unit.
    It uses classic recursive multiplication algorithm

    Parameters
    ----------
    dsp: DSPMulUnit
        dsp unit performing multiplications in single clock cycle
    n: int
        width of multiplied numbers
    """

    def __init__(self, dsp: DSPMulUnit, n: int):
        self.n = n
        self.dsp = dsp

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))
        self.confirm = Signal(reset=0)
        self.reset = Signal()

    def elaborate(self, platform):
        m = Module()
        if self.n <= self.dsp.n:
            with m.If(self.reset):
                m.d.sync += self.confirm.eq(0)

            with m.If(~self.confirm & ~self.reset):
                with Transaction().body(m):
                    res = self.dsp.compute(m, {"i1": self.i1, "i2": self.i2})
                    m.d.sync += self.result.eq(res)
                    m.d.sync += self.confirm.eq(1)
        else:
            m.submodules.low_mul = mul1 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)
            m.submodules.mid_mul = mul2 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)
            m.submodules.upper_mul = mul3 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)
            m.submodules.mul4 = mul4 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)

            m.d.comb += mul1.reset.eq(self.reset)
            m.d.comb += mul2.reset.eq(self.reset)
            m.d.comb += mul3.reset.eq(self.reset)
            m.d.comb += mul4.reset.eq(self.reset)

            m.d.comb += self.confirm.eq(mul1.confirm & mul2.confirm & mul3.confirm & mul4.confirm)

            signal_ll = Signal(unsigned(self.n))
            signal_ul = Signal(unsigned(self.n))
            signal_lu = Signal(unsigned(self.n))
            signal_uu = Signal(unsigned(self.n))

            m.d.comb += mul1.i1.eq(self.i1[: self.n // 2])
            m.d.comb += mul1.i2.eq(self.i2[: self.n // 2])
            m.d.comb += signal_ll.eq(mul1.result)

            m.d.comb += mul2.i1.eq(self.i1[self.n // 2 :])
            m.d.comb += mul2.i2.eq(self.i2[: self.n // 2])
            m.d.comb += signal_ul.eq(mul2.result)

            m.d.comb += mul3.i1.eq(self.i1[: self.n // 2])
            m.d.comb += mul3.i2.eq(self.i2[self.n // 2 :])
            m.d.comb += signal_lu.eq(mul3.result)

            m.d.comb += mul4.i1.eq(self.i1[self.n // 2 :])
            m.d.comb += mul4.i2.eq(self.i2[self.n // 2 :])
            m.d.comb += signal_uu.eq(mul4.result)

            m.d.comb += self.result.eq(signal_ll + ((signal_ul + signal_lu) << self.n // 2) + (signal_uu << self.n))

        return m


class SequentialUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing sequential multiplication using single DSP unit.
    It uses classic recursive multiplication algorithm
    """

    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        m.submodules.dsp = dsp = DSPMulUnit(self.gen.mul_unit_params.width)
        m.submodules.multiplier = multiplier = RecursiveWithSingleDSPMul(dsp, self.gen.isa.xlen)

        accepted = Signal(1, reset=1)
        confirm_counter = Signal(2)  # for 1 clock signal delay

        m.d.sync += multiplier.reset.eq(0)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += multiplier.i1.eq(arg.i1)
            m.d.sync += multiplier.i2.eq(arg.i2)

            m.d.sync += multiplier.reset.eq(1)
            m.d.sync += confirm_counter.eq(0)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~accepted) & (confirm_counter[1]))
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": multiplier.result}

        with m.If(~confirm_counter.all()):
            m.d.sync += confirm_counter.eq(confirm_counter + multiplier.confirm)

        return m


class FastRecursiveMul(Elaboratable):
    """
    Module with combinatorial connection for fast recursive multiplication using as many DSPMulUnit as required for
    one clock multiplication

    Parameters
    ----------
    n: int
        width of multiplied numbers
    dsp_width: int
        width of dsp multiplication unit
    """

    def __init__(self, n: int, dsp_width: int):
        self.n = n
        self.dsp_width = dsp_width

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.r = Signal(unsigned(n * 2))

    def elaborate(self, platform):
        m = Module()
        if self.n <= self.dsp_width:
            m.submodules.dsp = dsp = DSPMulUnit(self.dsp_width)
            with Transaction().body(m):
                res = dsp.compute(m, {"i1": self.i1, "i2": self.i2})
                m.d.comb += self.r.eq(res)
        else:
            upper = self.n // 2
            lower = (self.n + 1) // 2
            m.submodules.low_mul = low_mul = FastRecursiveMul(lower, self.dsp_width)
            m.submodules.mid_mul = mid_mul = FastRecursiveMul(lower + 1, self.dsp_width)
            m.submodules.upper_mul = upper_mul = FastRecursiveMul(upper, self.dsp_width)

            signal_low = Signal(unsigned(2 * lower))
            signal_mid = Signal(unsigned(2 * lower + 2))
            signal_upper = Signal(unsigned(2 * upper))

            m.d.comb += low_mul.i1.eq(self.i1[:lower])
            m.d.comb += low_mul.i2.eq(self.i2[:lower])
            m.d.comb += signal_low.eq(low_mul.r)

            m.d.comb += mid_mul.i1.eq(self.i1[:lower] + self.i1[lower:])
            m.d.comb += mid_mul.i2.eq(self.i2[:lower] + self.i2[lower:])
            m.d.comb += signal_mid.eq(mid_mul.r)

            m.d.comb += upper_mul.i1.eq(self.i1[lower:])
            m.d.comb += upper_mul.i2.eq(self.i2[lower:])
            m.d.comb += signal_upper.eq(upper_mul.r)

            m.d.comb += self.r.eq(
                signal_low + ((signal_mid - signal_low - signal_upper) << lower) + (signal_upper << 2 * lower)
            )

        return m


class RecursiveUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing fast recursive multiplication withing 1 clock cycle
    """

    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        res = Signal(unsigned(self.gen.isa.xlen * 2))

        i1 = Signal(unsigned(self.gen.isa.xlen))
        i2 = Signal(unsigned(self.gen.isa.xlen))
        accepted = Signal(1, reset=1)

        m.submodules.mul = mul = FastRecursiveMul(self.gen.isa.xlen, self.gen.mul_unit_params.width)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += i1.eq(arg.i1)
            m.d.sync += i2.eq(arg.i2)

            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~accepted))
        def _(arg):
            m.d.comb += mul.i1.eq(i1)
            m.d.comb += mul.i2.eq(i2)
            m.d.comb += res.eq(mul.r)
            m.d.sync += accepted.eq(1)
            return {"o": res}

        return m


class ShiftUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing cheap multi clock cycle multiplication using
    Russian Peasants Algorithm
    """

    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        res = Signal(unsigned(self.gen.isa.xlen * 2))

        i1 = Signal(unsigned(self.gen.isa.xlen * 2))
        i2 = Signal(unsigned(self.gen.isa.xlen))
        accepted = Signal(1, reset=1)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += res.eq(0)
            m.d.sync += i1.eq(arg.i1)
            m.d.sync += i2.eq(arg.i2)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~i2.bool() & ~accepted))
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": res}

        with m.If(~accepted):
            with m.If(i2[0]):
                m.d.sync += res.eq(res + i1)
            m.d.sync += i1.eq(i1 << 1)
            m.d.sync += i2.eq(i2 >> 1)

        return m
