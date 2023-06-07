from amaranth import *
from ..transactions import Method, def_method, TModule
from ..params import GenParams, ROBLayouts

__all__ = ["ReorderBuffer"]


class ReorderBuffer(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.params = gen_params
        layouts = gen_params.get(ROBLayouts)
        self.put = Method(i=layouts.data_layout, o=layouts.id_layout)
        self.mark_done = Method(i=layouts.mark_done_layout)
        self.peek = Method(o=layouts.peek_layout, nonexclusive=True)
        self.retire = Method(o=layouts.retire_layout)
        self.data = Array(Record(layouts.internal_layout) for _ in range(2**gen_params.rob_entries_bits))
        self.order_comparator = Method(i=layouts.order_comparator_i, o=layouts.order_comparator_o)

    def elaborate(self, platform):
        m = TModule()

        start_idx = Signal(self.params.rob_entries_bits)
        end_idx = Signal(self.params.rob_entries_bits)

        peek_possible = start_idx != end_idx
        put_possible = (end_idx + 1)[0 : len(end_idx)] != start_idx

        @def_method(m, self.peek, ready=peek_possible)
        def _():
            return {"rob_data": self.data[start_idx].rob_data, "rob_id": start_idx}

        @def_method(m, self.retire, ready=self.data[start_idx].done)
        def _():
            m.d.sync += start_idx.eq(start_idx + 1)
            m.d.sync += self.data[start_idx].done.eq(0)
            # TODO: because of a problem with mocking nonexclusive methods,
            # retire replicates functionality of peek
            return {"rob_data": self.data[start_idx].rob_data, "rob_id": start_idx}

        @def_method(m, self.put, ready=put_possible)
        def _(arg):
            m.d.sync += self.data[end_idx].rob_data.eq(arg)
            m.d.sync += self.data[end_idx].done.eq(0)
            m.d.sync += end_idx.eq(end_idx + 1)
            return end_idx

        # TODO: There is a potential race condition when ROB is flushed.
        # If functional units aren't flushed, finished obsolete instructions
        # could mark fields in ROB as done when they shouldn't.
        @def_method(m, self.mark_done)
        def _(rob_id: Value, exception):
            m.d.sync += self.data[rob_id].done.eq(1)
            m.d.sync += self.data[rob_id].exception.eq(exception)

        @def_method(m, self.order_comparator)
        def _(first_rob_id: Vaue, second_rob_id: Value) -> Value:
            return (first_rob_id - start_idx) < (second_rob_id - start_idx)

        return m
