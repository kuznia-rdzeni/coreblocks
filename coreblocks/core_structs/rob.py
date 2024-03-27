from amaranth import *
from transactron import Method, Transaction, def_method, TModule
from transactron.lib.metrics import *
from coreblocks.interface.layouts import ROBLayouts
from coreblocks.params import GenParams

__all__ = ["ReorderBuffer"]


class ReorderBuffer(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.params = gen_params
        layouts = gen_params.get(ROBLayouts)
        self.put = Method(i=layouts.data_layout, o=layouts.id_layout)
        self.mark_done = Method(i=layouts.mark_done_layout)
        self.peek = Method(o=layouts.peek_layout, nonexclusive=True)
        self.retire = Method()
        self.data = Array(Signal(layouts.internal_layout) for _ in range(2**gen_params.rob_entries_bits))
        self.get_indices = Method(o=layouts.get_indices, nonexclusive=True)

        self.perf_rob_wait_time = LatencyMeasurer(
            "backend.rob.wait_time",
            description="Distribution of time instructions spend in ROB",
            slots_number=(2**gen_params.rob_entries_bits + 1),
            max_latency=1000,
        )
        self.perf_rob_size = HwExpHistogram(
            "backend.rob.size",
            description="Number of instructions in ROB",
            bucket_count=gen_params.rob_entries_bits,
            sample_width=gen_params.rob_entries_bits + 1
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_rob_wait_time, self.perf_rob_size]

        start_idx = Signal(self.params.rob_entries_bits)
        end_idx = Signal(self.params.rob_entries_bits)

        peek_possible = start_idx != end_idx
        put_possible = (end_idx + 1)[0 : len(end_idx)] != start_idx

        @def_method(m, self.peek, ready=peek_possible)
        def _():
            return {
                "rob_data": self.data[start_idx].rob_data,
                "rob_id": start_idx,
                "exception": self.data[start_idx].exception,
            }

        @def_method(m, self.retire, ready=self.data[start_idx].done)
        def _():
            self.perf_rob_wait_time.stop(m)
            m.d.sync += start_idx.eq(start_idx + 1)
            m.d.sync += self.data[start_idx].done.eq(0)

        @def_method(m, self.put, ready=put_possible)
        def _(arg):
            self.perf_rob_wait_time.start(m)
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

        @def_method(m, self.get_indices)
        def _():
            return {"start": start_idx, "end": end_idx}

        if self.perf_rob_size.metrics_enabled():
            rob_size = Signal(self.params.rob_entries_bits + 1)
            m.d.comb += rob_size.eq(end_idx - start_idx)
            with Transaction(name="perf").body(m):
                self.perf_rob_size.add(m, rob_size)

        return m
