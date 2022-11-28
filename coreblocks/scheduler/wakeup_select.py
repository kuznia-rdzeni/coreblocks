from amaranth import *

from coreblocks.params import GenParams, FuncUnitLayouts
from coreblocks.utils import assign, AssignType
from coreblocks.transactions.core import *

__all__ = ["WakeupSelect"]


class WakeupSelect(Elaboratable):
    def __init__(self, *, gen_params: GenParams, get_ready: Method, take_row: Method, issue: Method):
        self.gen_params = gen_params
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

            row = self.take_row(m, last)
            issue_rec = Record(self.gen_params.get(FuncUnitLayouts).issue)
            m.d.comb += assign(issue_rec, row, fields=AssignType.ALL)
            self.issue(m, issue_rec)

        return m
