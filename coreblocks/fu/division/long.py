from amaranth import *
from coreblocks.transactions.core import def_method
from coreblocks.params import GenParams
from coreblocks.transactions import Transaction
from coreblocks.fu.division.common import DividerBase


class LongDividerUnit(Elaboratable):
    def __init__(self, n):
        self.bit_width = n

        self.num = Signal(unsigned(self.bit_width))
        self.den = Signal(unsigned(self.bit_width))

        self.quotient = Signal(unsigned(self.bit_width))
        self.remainder = Signal(unsigned(self.bit_width))
        self.valid = Signal(reset=0)
        self.reset = Signal()

    def elaborate(self, platform) -> Module:
        m = Module()
        num_cpy = Signal(unsigned(self.bit_width))
        m.d.sync += num_cpy.eq(self.num)

        with m.If(self.reset):
            m.d.sync += self.valid.eq(0)
            m.d.sync += self.quotient.eq(0)
            m.d.sync += self.remainder.eq(0)

        with m.If(~self.valid & ~self.reset):
            with Transaction().body(m):
                with m.If(num_cpy >= self.den):
                    m.d.sync += num_cpy.eq(num_cpy - self.den)
                    m.d.sync += self.quotient.eq(self.quotient + 1)

                with m.If(num_cpy < self.den):
                    m.d.sync += self.remainder.eq(num_cpy)
                    m.d.sync += self.valid.eq(1)
        return m


class LongDivider(DividerBase):
    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        m.submodules.divider = divider = LongDividerUnit(self.gen.isa.xlen)

        ready = Signal(1, reset=1)
        m.d.sync += divider.reset.eq(0)

        @def_method(m, self.issue, ready=ready)
        def _(arg):
            m.d.sync += divider.num.eq(arg.dividend)
            m.d.sync += divider.den.eq(arg.divisor)

            m.d.sync += divider.reset.eq(1)
            m.d.sync += ready.eq(0)

        @def_method(m, self.accept, ready=(~ready) & divider.valid & ~divider.reset)
        def _(arg):
            m.d.sync += ready.eq(1)
            return {"q": divider.quotient, "r": divider.remainder}

        return m
