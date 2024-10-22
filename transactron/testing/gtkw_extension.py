from typing import Iterable, Mapping
from contextlib import contextmanager
from amaranth.lib.data import View
from amaranth.sim.pysim import _VCDWriter
from amaranth.sim import Tick
from amaranth import *
from transactron.utils import flatten_signals


class _VCDWriterExt(_VCDWriter):
    def __init__(self, design, *, vcd_file, gtkw_file, traces):
        super().__init__(design=design, vcd_file=vcd_file, gtkw_file=gtkw_file, traces=list(flatten_signals(traces)))
        self._tree_traces = traces

    def close(self, timestamp):
        def save_signal(value: Value):
            for signal in value._rhs_signals():  # type: ignore
                if signal in self.gtkw_signal_names:
                    for name in self.gtkw_signal_names[signal]:
                        self.gtkw_save.trace(name)

        def gtkw_traces(traces):
            if isinstance(traces, Mapping):
                for k, v in traces.items():
                    with self.gtkw_save.group(k):
                        gtkw_traces(v)
            elif isinstance(traces, Iterable):
                for v in traces:
                    gtkw_traces(v)
            elif isinstance(traces, Record):
                if len(traces.fields) > 1:
                    with self.gtkw_save.group(traces.name):
                        for v in traces.fields.values():
                            gtkw_traces(v)
                elif len(traces.fields) == 1:  # to make gtkwave view less verbose
                    gtkw_traces(next(iter(traces.fields.values())))
            elif isinstance(traces, View):
                v = Value.cast(traces)
                with self.gtkw_save.group(v.name if isinstance(v, Signal) else ""):
                    save_signal(v)
            elif isinstance(traces, Value):
                save_signal(traces)

        if self.vcd_writer is not None:
            self.vcd_writer.close(timestamp)

        if self.gtkw_save is not None:
            self.gtkw_save.dumpfile(self.vcd_file.name)
            self.gtkw_save.dumpfile_size(self.vcd_file.tell())
            self.gtkw_save.zoom_markers(-21)

            self.gtkw_save.treeopen("top")
            gtkw_traces(self._tree_traces)

        if self.vcd_file is not None:
            self.vcd_file.close()
        if self.gtkw_file is not None:
            self.gtkw_file.close()


@contextmanager
def write_vcd_ext(engine, vcd_file, gtkw_file, traces):
    vcd_writer = _VCDWriterExt(engine._design, vcd_file=vcd_file, gtkw_file=gtkw_file, traces=traces)
    try:
        engine._vcd_writers.append(vcd_writer)
        yield Tick()
    finally:
        vcd_writer.close(engine.now)
        engine._vcd_writers.remove(vcd_writer)
