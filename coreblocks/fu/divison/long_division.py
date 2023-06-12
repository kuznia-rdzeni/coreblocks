from amaranth import *

from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
from coreblocks.params import GenParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.fu.divison.common import DividerBase

class RecursiveDivison(Elaboratable):
    def __init__(self, count: int, size: int):
        self.size = size
        self.n = count
        self.divisor = Signal(unsigned(size))
        self.dividend = Signal(unsigned(size))

        self.inp = Signal(unsigned(size))
        self.quotient = Signal(unsigned(size))
        self.remainder = Signal(unsigned(size))
        self.confirm = Signal(reset=0)

        self.reset = Signal()
        self.valid = Signal()

    def elaborate(self, platform) -> TModule:
        if self.n == 0:
            m = TModule()

            m.d.comb += self.quotient.eq(0)
            m.d.comb += self.remainder.eq(self.inp)

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
        m.d.comb += self.remainder.eq(rec_div.remainder)

        return m


class LongDivider(DividerBase):
    def __init__(self, gen: GenParams, stages=2):
        super().__init__(gen)
        self.stages = stages
        self.divisor_depth = self.gen.isa.xlen // stages

    def elaborate(self, platform):
        m = TModule()
        xlen = self.gen.isa.xlen

        m.submodules.divider = divider = RecursiveDivison(8, self.gen.isa.xlen)

        ready = Signal(1, reset=1)

        dividend = Signal(unsigned(xlen + 8))
        divisor = Signal(unsigned(xlen))

        quotient = Signal(unsigned(xlen))
        remainder = Signal(unsigned(xlen))

        stage = Signal(unsigned(xlen))

        @def_method(m, self.issue, ready=ready)
        def _(arg):
            m.d.sync += dividend.eq(arg.dividend)
            m.d.sync += divisor.eq(arg.divisor)
            m.d.sync += remainder.eq(0)
            m.d.sync += quotient.eq(0)
            m.d.sync += stage.eq(0)

            m.d.sync += ready.eq(0)
            

        @def_method(m, self.accept, ready=(~ready & stage == 4))
        def _(arg):
            m.d.sync += ready.eq(1)
            return {"quotient": quotient, "reminder": remainder}


        with m.If(~ready):
            m.d.comb += divider.divisor.eq(divisor)
            m.d.comb += divider.dividend.eq(
                (quotient << 8) | (dividend[xlen:] >> xlen)
            )
            m.d.comb += divider.inp.eq(remainder)

            m.d.sync += dividend.eq(dividend << 8)
            m.d.sync += remainder.eq(divider.remainder)
            m.d.sync += quotient.eq(divider.quotient)
            # m.d.sync += quotient.eq(0)

            m.d.sync += stage.eq(stage + 1)

        return m