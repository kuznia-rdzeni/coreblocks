from functools import reduce
import operator
from amaranth import *
from transactron import Method, Methods, Transaction, def_method, TModule, def_methods
from transactron.lib.fifo import WideFifo
from transactron.lib import logging
from transactron.lib.metrics import *
from coreblocks.interface.layouts import ROBLayouts
from coreblocks.params import GenParams

__all__ = ["ReorderBuffer"]

log = logging.HardwareLogger("core_structs.rob")


class ReorderBuffer(Elaboratable):
    """Reorder buffer.

    The reorder buffer (ROB) is a data structure responsible for preserving
    the original instruction order for the purpose of correctly freeing
    allocated registers and exception handling. The ROB is essentially
    a FIFO queue: the instructions are added to it in order by the scheduler
    (a part of the frontend) and removed in order by the retirement module
    (a part of the backend). Additionally, the ROB remembers which
    instructions finished execution: this information is updated by the
    announcement module.

    Attributes
    ----------
    put : Method
        Inserts instructions into the ROB. Used by the scheduler.
    mark_done : Methods
        Marks instruction as completed. Used by the announcement module.
    retire : Method
        Removes instructions from the ROB. Used by the retirement module.
    peek : Method
        Returns the front of the ROB without removing instructions.
    get_indices : Method
        Returns the `rob_id` of the oldest instruction in the ROB and the
        first `rob_id` after the newest instruction in the ROB.
    """

    def __init__(self, gen_params: GenParams, mark_done_ports: int) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Core generator parameters for the selected core configuration.
        mark_done_ports : int
            The number of `mark_done` methods (announcement ports).
        """
        self.params = gen_params
        layouts = gen_params.get(ROBLayouts)
        self.put = Method(i=layouts.put_layout, o=layouts.put_out_layout)
        self.mark_done = Methods(mark_done_ports, i=layouts.mark_done_layout)
        self.peek = Method(o=layouts.peek_layout)
        self.retire = Method(i=layouts.retire_layout)
        self.done = Array(Signal() for _ in range(2**self.params.rob_entries_bits))
        self.exception = Array(Signal() for _ in range(2**self.params.rob_entries_bits))
        self.data = WideFifo(
            shape=layouts.data_layout,
            depth=2**self.params.rob_entries_bits,
            read_width=self.params.retirement_superscalarity,
            write_width=self.params.frontend_superscalarity,
        )
        self.get_indices = Method(o=layouts.get_indices)

        self.perf_rob_wait_time = WideFIFOLatencyMeasurer(
            "backend.rob.wait_time",
            description="Distribution of time instructions spend in ROB",
            slots_number=(2**gen_params.rob_entries_bits + 1),
            max_latency=1000,
            max_start_count=gen_params.frontend_superscalarity,
            max_stop_count=gen_params.retirement_superscalarity,
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

        start_idx = Value.cast(self.data.read_idx)
        end_idx = Value.cast(self.data.write_idx)

        start_idx_plus = [Signal.like(start_idx) for _ in range(self.params.retirement_superscalarity)]
        for i in range(len(start_idx_plus)):
            m.d.comb += start_idx_plus[i].eq(start_idx + i)

        m.submodules.data = self.data

        with Transaction().body(m):
            peek_ret = self.data.peek(m)

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            entries = []
            for i in range(self.params.retirement_superscalarity):
                entries.append(
                    {
                        "rob_data": peek_ret.data[i],
                        "rob_id": start_idx_plus[i],
                        "exception": self.exception[start_idx_plus[i]],
                    }
                )
            return {"count": peek_ret.count, "entries": entries}

        @def_method(m, self.retire, ready=self.done[start_idx])
        def _(count: int):
            retire_ok = reduce(
                operator.and_,
                [self.done[start_idx_plus[i]] | (i >= count) for i in range(self.params.retirement_superscalarity)],
            )
            log.assertion(m, (count <= peek_ret.count) & retire_ok, "retire called with invalid count {}", count)
            self.perf_rob_wait_time.stop(m, count=count)
            self.data.read(m, count=count)
            for i in range(self.params.retirement_superscalarity):
                with m.If(i < count):
                    m.d.sync += self.done[start_idx_plus[i]].eq(0)

        @def_method(m, self.put)
        def _(count: int, entries):
            self.perf_rob_wait_time.start(m, count=count)
            self.data.write(m, count=count, data=entries)
            entries = []
            for i in range(self.params.frontend_superscalarity):
                rob_id = (end_idx + i)[: len(end_idx)]
                entries.append({"rob_id": rob_id})
            return {"entries": entries}

        # TODO: There is a potential race condition when ROB is flushed.
        # If functional units aren't flushed, finished obsolete instructions
        # could mark fields in ROB as done when they shouldn't.
        @def_methods(m, self.mark_done)
        def _(k: int, rob_id: Value, exception):
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
