from amaranth import *

from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
from coreblocks.params import GenParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method

__all__ = ["SequentialUnsignedMul"]


class RecursiveWithSingleDSPMul(Elaboratable):
    """
    Module with combinatorial connection for sequential multiplication using single DSP unit.
    It uses classic recursive multiplication algorithm.

    Attributes
    ----------
    i1: Signal(unsigned(n)), in
        First factor.
    i2: Signal(unsigned(n)), in
        Second factor.
    result: Signal(unsigned(n * 2)), out
        Product of inputted factors.
    confirm: Signal(1), out
        Signal providing information if computation is finished.
    reset: Signal(1), in
        Signal erasing previous result, and staring new computation of provided inputs.
    """

    def __init__(self, dsp: DSPMulUnit, n: int):
        """
        Parameters
        ----------
        dsp: DSPMulUnit
            Dsp unit performing multiplications in single clock cycle.
        n: int
            Bit width of multiplied numbers.
        """
        self.n = n
        self.dsp = dsp

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))
        self.confirm = Signal(reset=0)
        self.reset = Signal()

    def elaborate(self, platform) -> Module:
        if self.n <= self.dsp.n:
            m = Module()
            with m.If(self.reset):
                m.d.sync += self.confirm.eq(0)

            with m.If(~self.confirm & ~self.reset):
                with Transaction().body(m):
                    res = self.dsp.compute(m, {"i1": self.i1, "i2": self.i2})
                    m.d.sync += self.result.eq(res)
                    m.d.sync += self.confirm.eq(1)

            return m
        else:
            return self.recursive_module()

    def recursive_module(self) -> Module:
        # Classic Multiplying Algorythm
        #
        # bit: N       N/2      0
        #      +--------+-------+
        # i1 : | high_1 | low_1 |
        #      +--------+-------+
        # i2 : | high_2 | low_2 |
        #      +--------+-------+
        #
        #  result_ll = low_1 * low_2
        #  result_uu = high_1 * high_2
        #  result_lu = low_1 * high_2 +
        #  result_ul = high_1 * low_2
        #
        #  i1 * i2 = (high_1 << N/2 + low_1) * (high_2 << N/2 + low_2) =
        #          = (high_1 * high_2) << N + (high_1 * low_2 + high_2 * low_1) << N/2 + low_1 * low_2
        #          = result_uu << N + (result_lu + result_ul) << N/2 + result_ll

        m = Module()

        m.submodules.low_mul = mul1 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)
        m.submodules.mid_mul = mul2 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)
        m.submodules.upper_mul = mul3 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)
        m.submodules.mul4 = mul4 = RecursiveWithSingleDSPMul(self.dsp, self.n // 2)

        m.d.comb += mul1.reset.eq(self.reset)
        m.d.comb += mul2.reset.eq(self.reset)
        m.d.comb += mul3.reset.eq(self.reset)
        m.d.comb += mul4.reset.eq(self.reset)

        m.d.comb += self.confirm.eq(mul1.confirm & mul2.confirm & mul3.confirm & mul4.confirm)

        result_ll = Signal(unsigned(self.n))
        result_ul = Signal(unsigned(self.n))
        result_lu = Signal(unsigned(self.n))
        result_uu = Signal(unsigned(self.n))

        m.d.comb += mul1.i1.eq(self.i1[: self.n // 2])
        m.d.comb += mul1.i2.eq(self.i2[: self.n // 2])
        m.d.comb += result_ll.eq(mul1.result)

        m.d.comb += mul2.i1.eq(self.i1[self.n // 2 :])
        m.d.comb += mul2.i2.eq(self.i2[: self.n // 2])
        m.d.comb += result_ul.eq(mul2.result)

        m.d.comb += mul3.i1.eq(self.i1[: self.n // 2])
        m.d.comb += mul3.i2.eq(self.i2[self.n // 2 :])
        m.d.comb += result_lu.eq(mul3.result)

        m.d.comb += mul4.i1.eq(self.i1[self.n // 2 :])
        m.d.comb += mul4.i2.eq(self.i2[self.n // 2 :])
        m.d.comb += result_uu.eq(mul4.result)

        m.d.comb += self.result.eq(result_ll + ((result_ul + result_lu) << self.n // 2) + (result_uu << self.n))

        return m


class SequentialUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing sequential multiplication using single DSP unit.
    It uses classic recursive multiplication algorithm.
    """

    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        m.submodules.dsp = dsp = DSPMulUnit(self.gen.mul_unit_params.width)
        m.submodules.multiplier = multiplier = RecursiveWithSingleDSPMul(dsp, self.gen.isa.xlen)

        accepted = Signal(1, reset=1)
        m.d.sync += multiplier.reset.eq(0)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += multiplier.i1.eq(arg.i1)
            m.d.sync += multiplier.i2.eq(arg.i2)

            m.d.sync += multiplier.reset.eq(1)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~accepted) & multiplier.confirm & ~multiplier.reset)
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": multiplier.result}

        return m
