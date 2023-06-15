from amaranth import *

from coreblocks.params import GenParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.fu.divison.common import DividerBase


class RecursiveDivison(Elaboratable):
    def __init__(self, count: int, size: int, remainder_early_return: int = 0):
        self.size = size
        self.n = count
        self.remainder_early_return = remainder_early_return

        self.divisor = Signal(unsigned(size))
        self.dividend = Signal(unsigned(size))
        self.inp = Signal(unsigned(size))

        self.quotient = Signal(unsigned(size))
        self.remainder = Signal(unsigned(size))
        self.partial_reminder = Signal(unsigned(size))

    def elaborate(self, platform) -> TModule:
        if self.n == 0:
            m = TModule()

            m.d.comb += self.quotient.eq(0)
            m.d.comb += self.remainder.eq(self.inp)
            m.d.comb += self.partial_reminder.eq(self.inp)

            return m
        else:
            return self.recursive_module()

    def recursive_module(self) -> TModule:
        m = TModule()

        concat = Signal(self.size)
        m.d.comb += concat.eq((self.inp << 1) | self.dividend[self.n - 1])

        m.submodules.rec_div = rec_div = RecursiveDivison(
            self.n - 1, self.size, remainder_early_return=self.remainder_early_return - 1
        )

        m.d.comb += rec_div.dividend.eq(self.dividend)
        m.d.comb += rec_div.divisor.eq(self.divisor)

        with m.If(concat >= self.divisor):
            m.d.comb += self.quotient[self.n - 1].eq(1)
            m.d.comb += rec_div.inp.eq(concat - self.divisor)
        with m.Else():
            m.d.comb += self.quotient[self.n - 1].eq(0)
            m.d.comb += rec_div.inp.eq(concat)

        m.d.comb += self.quotient[: (self.n - 1)].eq(rec_div.quotient)
        m.d.comb += self.remainder.eq(rec_div.remainder)

        if self.remainder_early_return == 0:
            m.d.comb += self.partial_reminder.eq(self.inp)
        else:
            m.d.comb += self.partial_reminder.eq(rec_div.partial_reminder)

        return m


class LongDivider(DividerBase):
    def __init__(self, gen: GenParams, ipc=4):
        super().__init__(gen)
        xlen = self.gen.isa.xlen

        self.ipc = ipc
        self.divisor_depth = ipc
        self.remainder_early_return = xlen % ipc

        self.stages = xlen // ipc + (1 if self.remainder_early_return > 0 else 0)
        self.odd_iteration = self.remainder_early_return != 0

    def elaborate(self, platform):
        m = TModule()
        xlen = self.gen.isa.xlen
        xlen_log = self.gen.isa.xlen_log

        m.submodules.divider = divider = RecursiveDivison(
            self.ipc, xlen, remainder_early_return=self.remainder_early_return
        )

        ready = Signal(1, reset=1)

        dividend = Signal(unsigned(xlen))
        divisor = Signal(unsigned(xlen))

        quotient = Signal(unsigned(xlen))
        remainder = Signal(unsigned(xlen))

        stage = Signal(unsigned(xlen_log + 1))

        @def_method(m, self.issue, ready=ready)
        def _(arg):
            m.d.sync += dividend.eq(arg.dividend)
            m.d.sync += divisor.eq(arg.divisor)
            m.d.sync += remainder.eq(0)
            m.d.sync += quotient.eq(0)
            m.d.sync += stage.eq(0)

            m.d.sync += ready.eq(0)

        @def_method(m, self.accept, ready=(~ready & (stage == self.stages)))
        def _(arg):
            m.d.sync += ready.eq(1)
            return {"quotient": quotient, "reminder": remainder}

        with m.If(~ready & (stage < self.stages)):
            special_stage = (self.stages == stage + 1) & self.odd_iteration

            m.d.comb += divider.divisor.eq(divisor)
            m.d.comb += divider.dividend.eq(dividend[xlen - self.ipc :])
            m.d.comb += divider.inp.eq(remainder)

            m.d.sync += dividend.eq(dividend << self.ipc)

            with m.If(special_stage):
                m.d.sync += remainder.eq(divider.partial_reminder)
                m.d.sync += quotient.eq(
                    Cat(divider.quotient[self.ipc - self.remainder_early_return : self.ipc], quotient)
                )
            with m.Else():
                m.d.sync += remainder.eq(divider.remainder)
                m.d.sync += quotient.eq(Cat(divider.quotient[: self.ipc], quotient))

            m.d.sync += stage.eq(stage + 1)

        return m
