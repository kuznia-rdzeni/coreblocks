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

    Attributes
    ----------
    i1: Signal(unsigned(n)), in
        First factor.
    i2: Signal(unsigned(n)), in
        Second factor.
    r: Signal(unsigned(n * 2)), out
        Product of inputted factors.
    """

    def __init__(self, n: int, dsp_width: int):
        """
        Parameters
        ----------
        n: int
            Bit width of multiplied numbers.
        dsp_width: int
            Bit width of number multiplied bu dsp unit.
        """
        self.n = n
        self.dsp_width = dsp_width

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.r = Signal(unsigned(n * 2))

    def elaborate(self, platform) -> Module:
        if self.n <= self.dsp_width:
            m = Module()
            m.submodules.dsp = dsp = DSPMulUnit(self.dsp_width)
            with Transaction().body(m):
                # The bit width of the `i1` and `i2` parameters of `dsp` is different than of `self.i1`
                # and `self.i2`, which triggers an error. Using `| 0` silences it.
                res = dsp.compute(m, i1=self.i1 | 0, i2=self.i2 | 0)
                m.d.comb += self.r.eq(res)

            return m
        else:
            return self.recursive_module()

    def recursive_module(self) -> Module:
        # Fast Recursive Multiplying Algorythm
        #
        # bit: N       N/2      0
        #      +--------+-------+
        # i1 : | high_1 | low_1 |
        #      +--------+-------+
        # i2 : | high_2 | low_2 |
        #      +--------+-------+
        #
        #  result_low   = low_1 * low_2
        #  result_upper = high_1 * high_2
        #  result_mid   = (low_1 + high_1) * (low_2 + high_2) =
        #               = low_1 * low_2 + high_1 * high_2 + low_1 * high_2 + low_2 * high_1
        #               = result_low + result_upper + low_1 * high_2 + low_2 * high_1
        #
        #  i1 * i2 = (high_1 << N/2 + low_1) * (high_2 << N/2 + low_2) =
        #          = (high_1 * high_2) << N + (high_1 * low_2 + high_2 * low_1) << N/2 + low_1 * low_2 =
        #          = result_upper << N + (result_mid - result_low - result_upper) << N/2 + result_low

        m = Module()

        upper = self.n // 2
        lower = (self.n + 1) // 2
        m.submodules.low_mul = low_mul = FastRecursiveMul(lower, self.dsp_width)
        m.submodules.mid_mul = mid_mul = FastRecursiveMul(lower + 1, self.dsp_width)
        m.submodules.upper_mul = upper_mul = FastRecursiveMul(upper, self.dsp_width)

        result_low = Signal(unsigned(2 * lower))
        result_mid = Signal(unsigned(2 * lower + 2))
        result_upper = Signal(unsigned(2 * upper))

        m.d.comb += low_mul.i1.eq(self.i1[:lower])
        m.d.comb += low_mul.i2.eq(self.i2[:lower])
        m.d.comb += result_low.eq(low_mul.r)

        m.d.comb += mid_mul.i1.eq(self.i1[:lower] + self.i1[lower:])
        m.d.comb += mid_mul.i2.eq(self.i2[:lower] + self.i2[lower:])
        m.d.comb += result_mid.eq(mid_mul.r)

        m.d.comb += upper_mul.i1.eq(self.i1[lower:])
        m.d.comb += upper_mul.i2.eq(self.i2[lower:])
        m.d.comb += result_upper.eq(upper_mul.r)

        m.d.comb += self.r.eq(
            result_low + ((result_mid - result_low - result_upper) << lower) + (result_upper << 2 * lower)
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
            fifo.write(m, o=mul.r)

        @def_method(m, self.accept)
        def _(arg):
            return fifo.read(m)

        return m
