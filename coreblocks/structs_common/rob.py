from amaranth import *
from ..transactions import Method, def_method, Priority, TModule
from ..params import GenParams, ROBLayouts

__all__ = ["ReorderBuffer"]


class ReorderBuffer(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.params = gen_params
        layouts = gen_params.get(ROBLayouts)
        self.put = Method(i=layouts.data_layout, o=layouts.id_layout)
        self.mark_done = Method(i=layouts.id_layout)
        self.peek = Method(o=layouts.peek_layout, nonexclusive=True)
        self.retire = Method(o=layouts.retire_layout)
        self.empty = Method(o=layouts.empty, nonexclusive=True)
        self.flush = Method(o=layouts.flush_layout)
        self.data = Array(Record(layouts.internal_layout) for _ in range(2**gen_params.rob_entries_bits))

    def free_entry(self, m, start_idx):
        m.d.sync += start_idx.eq(start_idx + 1)
        m.d.sync += self.data[start_idx].done.eq(0)

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

        self.flush.add_conflict(self.put, priority=Priority.LEFT)
        self.flush.add_conflict(self.retire, priority=Priority.LEFT)

        # TODO: rework flushing so that it's handled by some other block
        # or ROB itself (rather than interrupt coordinator). This should
        # be easier when we switch to one-cycle ROB flushing method that
        # just restores a pointer in free-RF-list since we won't have to
        # recycle physical register ids back during flushing
        @def_method(m, self.flush)
        def _():
            m.d.sync += start_idx.eq(start_idx + 1)
            m.d.sync += self.data[start_idx].done.eq(0)
            entry = self.data[start_idx].rob_data
            return {
                "rp_dst": entry.rp_dst,
                "pc": entry.pc,
            }

        # TODO: There is a potential race condition when ROB is flushed.
        # If functional units aren't flushed, finished obsolete instructions
        # could mark fields in ROB as done when they shouldn't.
        @def_method(m, self.mark_done)
        def _(rob_id: Value):
            m.d.sync += self.data[rob_id].done.eq(1)

        return m
