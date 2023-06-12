from amaranth import *

from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
from coreblocks.params import GenParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method

__all__ = ["SequentialUnsignedMul"]


class RecursiveDivison(Elaboratable):
    def __init__(self, n: int, size: int):
        """
        Parameters
        ----------
        dsp: DSPMulUnit
            Dsp unit performing multiplications in single clock cycle.
        n: int
            Bit width of multiplied numbers.
        """
        self.size = size
        self.n = n
        self.divisor = Signal(unsigned(size))
        self.dividend = Signal(unsigned(size))

        self.inp = Signal(unsigned(size))
        self.quotient = Signal(unsigned(size))
        self.reminder = Signal(unsigned(size))
        self.confirm = Signal(reset=0)
        self.reset = Signal()

    def elaborate(self, platform) -> TModule:
        if self.n == 0:
            m = TModule()

            m.d.comb += self.quotient.eq(0)
            m.d.comb += self.reminder.eq(self.inp)

            return m
        else:
            return self.recursive_module()

    def recursive_module(self) -> TModule:
        m = TModule()

        concat = Signal(self.size)
        m.d.comb += concat.eq((self.inp << 1) | self.dividend[self.n - 1])

        m.submodules.rec_div = rec_div = RecursiveDivison(self.n - 1, self.size)

        m.d.comb += rec_div.dividend.eq(self.dividend)
        m.d.comb += rec_div.divisor.eq(self.divisor)


        with m.If(concat >= self.divisor):
            m.d.comb += self.quotient[self.n - 1].eq(1)
            m.d.comb += rec_div.inp.eq(concat - self.divisor)
        with m.Else():
            m.d.comb += self.quotient[self.n - 1].eq(0)
            m.d.comb += rec_div.inp.eq(concat)
        
        m.d.comb += self.quotient[:(self.n - 1)].eq(rec_div.quotient)
        m.d.comb += self.reminder.eq(rec_div.reminder)

        return m


class SequentialUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing sequential multiplication using single DSP unit.
    It uses classic recursive multiplication algorithm.
    """

    def __init__(self, gen: GenParams, dsp_width: int = 8):
        super().__init__(gen)
        self.dsp_width = dsp_width

    def elaborate(self, platform):
        m = TModule()
        m.submodules.dsp = dsp = DSPMulUnit(self.dsp_width)
        m.submodules.multiplier = multiplier = RecursiveDivison(self.gen.isa.xlen, 0)

        accepted = Signal(1, reset=1)
        m.d.sync += multiplier.reset.eq(0)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += multiplier.dividend.eq(arg.i1)
            m.d.sync += multiplier.quotient.eq(arg.i2)
            m.d.sync += multiplier.inp.eq(0)

            m.d.sync += multiplier.reset.eq(1)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~accepted) & multiplier.confirm & ~multiplier.reset)
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": multiplier.quotient}

        return m
