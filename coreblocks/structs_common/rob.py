from amaranth import *
from transactron import Method, def_method, TModule
from transactron.core import Priority
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
        self.empty = Method(o=layouts.empty, nonexclusive=True)
        self.flush_one = Method(o=layouts.flush_layout)
        self.get_indices = Method(o=layouts.get_indices, nonexclusive=True)
        self.data = Array(Record(layouts.internal_layout) for _ in range(2**gen_params.rob_entries_bits))

    def elaborate(self, platform):
        m = TModule()

        start_idx = Signal(self.params.rob_entries_bits)
        end_idx = Signal(self.params.rob_entries_bits)

        empty = start_idx == end_idx
        put_possible = (end_idx + 1)[0 : len(end_idx)] != start_idx

        @def_method(m, self.peek, ready=~empty)
        def _():
            return {
                "rob_data": self.data[start_idx].rob_data,
                "rob_id": start_idx,
                "exception": self.data[start_idx].exception,
            }

        @def_method(m, self.retire, ready=self.data[start_idx].done)
        def _():
            m.d.sync += start_idx.eq(start_idx + 1)
            m.d.sync += self.data[start_idx].done.eq(0)
            # TODO: because of a problem with mocking nonexclusive methods,
            # retire replicates functionality of peek
            return {
                "rob_data": self.data[start_idx].rob_data,
                "rob_id": start_idx,
                "exception": self.data[start_idx].exception,
            }

        @def_method(m, self.put, ready=put_possible)
        def _(arg):
            m.d.sync += self.data[end_idx].rob_data.eq(arg)
            m.d.sync += self.data[end_idx].done.eq(0)
            m.d.sync += end_idx.eq(end_idx + 1)
            return end_idx

        @def_method(m, self.empty)
        def _():
            return empty

        self.flush_one.add_conflict(self.put, priority=Priority.LEFT)
        self.flush_one.add_conflict(self.retire, priority=Priority.LEFT)

        # TODO: rework flushing so that it's handled by some other block
        # or ROB itself (rather than interrupt coordinator). This should
        # be easier when we switch to one-cycle ROB flushing method that
        # just restores a pointer in free-RF-list since we won't have to
        # recycle physical register ids back during flushing
        @def_method(m, self.flush_one)
        def _():
            m.d.sync += start_idx.eq(start_idx + 1)
            m.d.sync += self.data[start_idx].done.eq(0)
            entry = self.data[start_idx].rob_data
            return {"rp_dst": entry.rp_dst}

        # For correctness, flushing functional units needs to be done to
        # avoid marking entries in the ROB that don't correspond to them
        # anymore because they got flushed - this is currently implemented
        @def_method(m, self.mark_done)
        def _(rob_id: Value, exception):
            m.d.sync += self.data[rob_id].done.eq(1)
            m.d.sync += self.data[rob_id].exception.eq(exception)

        @def_method(m, self.get_indices)
        def _():
            return {"start": start_idx, "end": end_idx}

        return m
