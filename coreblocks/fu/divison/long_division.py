from amaranth import *

from coreblocks.params import GenParams
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.fu.divison.common import DividerBase

"""
Algorithm - multi-cycle array divider
Method described here: https://yuhei1-horibe.medium.com/designing-divider-213fbd32beb2
"""


class RecursiveDivison(Elaboratable):
    """
    Module that calculates n bits of quotient and
    yields remainder that can be used in next iteration

    If count == xlen the module is basically a one-cycle divider

    If count if not aligned to power of 2, then in last iteration we need to calculate
    different amount of bits.
    So to optimize resource usage, there is partial reminder
    that allows to reuse this module for a shorter calculation.

    Attributes
    ----------
    size: int
        Size of inputs
    n: int
        Number of steps
    partial_remainder_count: int
        Number of steps for last iteration
    divisor: Signal
        Input divisor
    dividend: Signal
        Input dividend
    input_remainder: Signal
        Remainder carried over from previous iteration
    quotient: Signal
        Calculated n bits of quotient
    remainder: Signal
        Calculated remainder
    partial_remainder: Signal
        Calculated partial reminder
    """

    def __init__(self, step_count: int, size: int, partial_remainder_count: int = 0):
        self.size = size
        self.step_count = step_count
        self.partial_remainder_count = partial_remainder_count

        self.divisor = Signal(unsigned(size))
        self.dividend = Signal(unsigned(size))
        self.input_remainder = Signal(unsigned(size))

        self.quotient = Signal(unsigned(size))
        self.remainder = Signal(unsigned(size))
        self.partial_reminder = Signal(unsigned(size))

    def elaborate(self, platform) -> TModule:
        if self.step_count == 0:
            # default case
            m = TModule()

            m.d.comb += self.quotient.eq(0)
            m.d.comb += self.remainder.eq(self.input_remainder)
            m.d.comb += self.partial_reminder.eq(self.input_remainder)

            return m
        else:
            return self.recursive_module()

    def recursive_module(self) -> TModule:
        m = TModule()

        # adding bit from dividend
        concat = Signal(self.size)
        m.d.comb += concat.eq(Cat(self.dividend[self.step_count - 1], self.input_remainder))

        # recursive module
        m.submodules.rec_div = rec_div = RecursiveDivison(
            self.step_count - 1, self.size, partial_remainder_count=self.partial_remainder_count - 1
        )

        m.d.comb += rec_div.dividend.eq(self.dividend)
        m.d.comb += rec_div.divisor.eq(self.divisor)

        # Single step as described in article
        with m.If(concat >= self.divisor):
            m.d.comb += self.quotient[self.step_count - 1].eq(1)
            m.d.comb += rec_div.input_remainder.eq(concat - self.divisor)
        with m.Else():
            m.d.comb += self.quotient[self.step_count - 1].eq(0)
            m.d.comb += rec_div.input_remainder.eq(concat)

        # wiring up rest of result from recursive module
        m.d.comb += self.quotient[: (self.step_count - 1)].eq(rec_div.quotient)
        m.d.comb += self.remainder.eq(rec_div.remainder)

        # partial remainder
        if self.partial_remainder_count == 0:
            m.d.comb += self.partial_reminder.eq(self.input_remainder)
        else:
            m.d.comb += self.partial_reminder.eq(rec_div.partial_reminder)

        return m


class LongDivider(DividerBase):
    """
    Module that handles iterative calculation

    Attributes
    ----------
    gen_params: GenParams
        Gen Params
    ipc: int
        Number of steps per cycle
    partial_remainder_count: int
        Depth of last iteration
    stages: int
        Number of required iterations
    odd_iteration: bool
        flag whether last iteration requires partial calculation
    """

    def __init__(self, gen_params: GenParams, ipc=4):
        super().__init__(gen_params)
        xlen = self.gen_params.isa.xlen

        self.ipc = ipc
        self.partial_remainder_count = xlen % ipc

        self.stages = xlen // ipc + (1 if self.partial_remainder_count > 0 else 0)
        self.odd_iteration = self.partial_remainder_count != 0

    def elaborate(self, platform):
        m = TModule()
        xlen = self.gen_params.isa.xlen
        xlen_log = self.gen_params.isa.xlen_log

        m.submodules.divider = divider = RecursiveDivison(
            self.ipc, xlen, partial_remainder_count=self.partial_remainder_count
        )

        ready = Signal(1, reset=1)

        dividend = Signal(unsigned(xlen))
        divisor = Signal(unsigned(xlen))

        quotient = Signal(unsigned(xlen))
        remainder = Signal(unsigned(xlen))

        stage = Signal(unsigned(xlen_log + 1))

        # resetting
        @def_method(m, self.issue, ready=ready)
        def _(arg):
            m.d.sync += dividend.eq(arg.dividend)
            m.d.sync += divisor.eq(arg.divisor)
            m.d.sync += remainder.eq(0)
            m.d.sync += quotient.eq(0)
            m.d.sync += stage.eq(0)

            m.d.sync += ready.eq(0)

        # returning results
        @def_method(m, self.accept, ready=(~ready & (stage == self.stages)))
        def _(arg):
            m.d.sync += ready.eq(1)
            return {"quotient": quotient, "remainder": remainder}

        # performing calculations
        with m.If(~ready & (stage < self.stages)):
            special_stage = (self.stages == stage + 1) & self.odd_iteration

            # assigning inputs to recursive divider
            m.d.comb += divider.divisor.eq(divisor)
            m.d.comb += divider.dividend.eq(dividend[xlen - self.ipc :])
            m.d.comb += divider.input_remainder.eq(remainder)

            # dividend is a shift register
            # so in each iteration upper bits are fed into recursive divider
            m.d.sync += dividend.eq(dividend << self.ipc)

            # if we are in the last stage and uneven amount of bits needs to be handled
            with m.If(special_stage):
                m.d.sync += remainder.eq(divider.partial_reminder)
                m.d.sync += quotient.eq(
                    Cat(divider.quotient[self.ipc - self.partial_remainder_count : self.ipc], quotient)
                )
            # normal iteration
            with m.Else():
                m.d.sync += remainder.eq(divider.remainder)
                m.d.sync += quotient.eq(Cat(divider.quotient[: self.ipc], quotient))

            m.d.sync += stage.eq(stage + 1)

        return m
