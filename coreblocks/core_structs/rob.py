from amaranth import *
import amaranth.lib.memory as memory
from transactron import Method, Transaction, def_method, TModule
from transactron.lib import logging
from transactron.lib.metrics import *
from coreblocks.interface.layouts import ROBLayouts
from coreblocks.params import GenParams

__all__ = ["ReorderBuffer"]

log = logging.HardwareLogger("core_structs.rob")


class ReorderBuffer(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.params = gen_params
        layouts = gen_params.get(ROBLayouts)
        self.put = Method(i=layouts.data_layout, o=layouts.id_layout)
        self.mark_done = Method(i=layouts.mark_done_layout)
        self.peek = Method(o=layouts.peek_layout)
        self.retire = Method()
        self.done = Array(Signal() for _ in range(2**self.params.rob_entries_bits))
        self.exception = Array(Signal() for _ in range(2**self.params.rob_entries_bits))
        self.data = memory.Memory(shape=layouts.data_layout, depth=2**self.params.rob_entries_bits, init=[])
        self.get_indices = Method(o=layouts.get_indices)

        self.perf_rob_wait_time = FIFOLatencyMeasurer(
            "backend.rob.wait_time",
            description="Distribution of time instructions spend in ROB",
            slots_number=(2**gen_params.rob_entries_bits + 1),
            max_latency=1000,
        )
        self.perf_rob_size = HwExpHistogram(
            "backend.rob.size",
            description="Number of instructions in ROB",
            bucket_count=gen_params.rob_entries_bits + 1,
            sample_width=gen_params.rob_entries_bits,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_rob_wait_time, self.perf_rob_size]

        start_idx = Signal(self.params.rob_entries_bits)
        end_idx = Signal(self.params.rob_entries_bits)

        peek_possible = start_idx != end_idx
        put_possible = (end_idx + 1)[0 : len(end_idx)] != start_idx

        m.submodules.data = self.data
        write_port = self.data.write_port()
        read_port = self.data.read_port(transparent_for=[write_port])

        m.d.comb += read_port.addr.eq(start_idx)

        @def_method(m, self.peek, ready=peek_possible, nonexclusive=True)
        def _():
            return {
                "rob_data": read_port.data,
                "rob_id": start_idx,
                "exception": self.exception[start_idx],
            }

        @def_method(m, self.retire, ready=self.done[start_idx])
        def _():
            self.perf_rob_wait_time.stop(m)
            m.d.sync += start_idx.eq(start_idx + 1)
            m.d.comb += read_port.addr.eq(start_idx + 1)
            m.d.sync += self.done[start_idx].eq(0)

        @def_method(m, self.put, ready=put_possible)
        def _(arg):
            self.perf_rob_wait_time.start(m)
            m.d.av_comb += write_port.addr.eq(end_idx)
            m.d.av_comb += write_port.data.eq(arg)
            m.d.comb += write_port.en.eq(1)
            m.d.sync += end_idx.eq(end_idx + 1)
            return end_idx

        # TODO: There is a potential race condition when ROB is flushed.
        # If functional units aren't flushed, finished obsolete instructions
        # could mark fields in ROB as done when they shouldn't.
        @def_method(m, self.mark_done)
        def _(rob_id: Value, exception):
            log.assertion(m, ~self.done[rob_id], "mark_done called on already done ROB entry {}", rob_id)
            m.d.sync += self.done[rob_id].eq(1)
            m.d.sync += self.exception[rob_id].eq(exception)

        @def_method(m, self.get_indices, nonexclusive=True)
        def _():
            return {"start": start_idx, "end": end_idx}

        if self.perf_rob_size.metrics_enabled():
            rob_size = Signal(self.params.rob_entries_bits)
            m.d.comb += rob_size.eq((end_idx - start_idx)[0 : self.params.rob_entries_bits])
            with Transaction(name="perf").body(m):
                self.perf_rob_size.add(m, rob_size)

        return m
