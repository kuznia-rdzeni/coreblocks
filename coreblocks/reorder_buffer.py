from . import transactions as ts
from .transactions import lib as tl
from amaranth import *

from .genparams import GenParams
from .layouts import ROBLayouts
from coreblocks import genparams


class ReorderBuffer(Elaboratable):
    def __init__(self, gen_params : GenParams) -> None:
        self.params = gen_params
        self.layouts = ROBLayouts(gen_params)
        self.put = ts.Method(i=self.layouts.data_layout, o=self.layouts.id_layout)
        self.mark_done = ts.Method(i=self.layouts.id_layout)
        self.retire = ts.Method(o=self.layouts.data_layout)
        self.data = Array(Record(self.layouts.internal_layout) for _ in range(2**gen_params.rob_entries_bits))


    def elaborate(self, platform) -> Module:
        m = Module()

        start_cnt = Signal(self.params.rob_entries_bits)
        end_cnt = Signal(self.params.rob_entries_bits)

        put_possible = end_cnt != start_cnt - 1

        @tl.def_method(m, self.retire, ready=self.data[start_cnt].done)
        def _(arg):
            m.d.sync += start_cnt.eq(start_cnt + 1)
            m.d.sync += self.data[start_cnt].done.eq(0)
            return self.data[start_cnt].rob_data

        @tl.def_method(m, self.put, ready=put_possible)
        def _(arg):
            m.d.sync += self.data[end_cnt].rob_data.eq(arg)
            m.d.sync += self.data[end_cnt].done.eq(0)
            m.d.sync += end_cnt.eq(end_cnt + 1)
            return end_cnt

        # TODO: There is a potential race condition when ROB is flushed.
        # If functional units aren't flushed, finished obsolete instructions
        # could mark fields in ROB as done when they shouldn't.
        @tl.def_method(m, self.mark_done)
        def _(arg):
            m.d.sync += self.data[arg.rob_id].done.eq(1)

        return m
