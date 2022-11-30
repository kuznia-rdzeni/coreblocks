from amaranth import *

from coreblocks.fu.unsigned_multiplication.common import MulBaseUnsigned, DSPMulUnit
from coreblocks.params import GenParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method

__all__ = ["RecursiveUnsignedMul"]

from coreblocks.transactions.lib import FIFO


class FastRecursiveMul(Elaboratable):
    """
    Module with combinatorial connection for fast recursive multiplication using as many DSPMulUnit as required for
    one clock multiplication.

    Parameters
    ----------
    n: int
        Bit width of multiplied numbers.
    dsp_width: int
        Bit width of number multiplied bu dsp unit.
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
    Module with @see{MulBaseUnsigned} interface performing fast recursive multiplication within 1 clock cycle.
    """

    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        m.submodules.fifo = fifo = FIFO([("o", 2 * self.gen.isa.xlen)], 2)

        m.submodules.mul = mul = FastRecursiveMul(self.gen.isa.xlen, self.gen.mul_unit_params.width)

        @def_method(m, self.issue)
        def _(arg):
            m.d.comb += mul.i1.eq(arg.i1)
            m.d.comb += mul.i2.eq(arg.i2)
            fifo.write(m, {"o": mul.r})

        @def_method(m, self.accept)
        def _(arg):
            return fifo.read(m)

        return m
