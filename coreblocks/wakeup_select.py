from amaranth import *

from coreblocks.transactions.core import *


class WakeupSelect(Elaboratable):
    def __init__(self, *, get_ready, take_row, issue):
        self.get_ready = get_ready  # assumption: ready only if nonzero result
        self.take_row = take_row
        self.issue = issue

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            ready = self.get_ready(m)
            ready_width = len(ready)
            last = Signal(range(ready_width))
            for i in range(ready_width):
                with m.If(ready[i]):
                    m.d.comb += last.eq(i)
            self.issue(m, self.take_row(m, last))

        return m
