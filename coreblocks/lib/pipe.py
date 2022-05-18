from amaranth import *
from coreblocks.transactions._utils import *

all = ["PipeEndpoint", "Pipe"]


class PipeEndpoint(Record):
    def __init__(self, layout):
        super().__init__(
            [
                ("ready", 1),
                ("valid", 1),
                ("payload", _coerce_layout(layout)),
            ]
        )


class Pipe(Elaboratable):
    def __init__(self, layout):
        self.sink = PipeEndpoint(layout)
        self.source = PipeEndpoint(layout)

    def elaborate(self, platform):
        m = Module()

        buf = Record.like(self.source.payload)
        buf_valid = Signal()

        sink_ready = self.sink.ready | ~self.sink.valid
        m.d.sync += self.source.ready.eq(sink_ready | (~buf_valid & ~self.source.valid))

        with m.If(self.source.ready):
            # Input is ready
            with m.If(sink_ready):
                # Output is ready or currently not valid, transfer data to output
                m.d.sync += self.sink.valid.eq(self.source.valid)
                m.d.sync += self.sink.payload.eq(self.source.payload)
            with m.Else():
                # Output is not ready, store input in buffer
                m.d.sync += buf_valid.eq(self.source.valid)
                m.d.sync += buf.eq(self.source.payload)
        with m.Elif(sink_ready):
            # Input is not ready, but output is ready
            m.d.sync += self.sink.valid.eq(buf_valid)
            m.d.sync += self.sink.payload.eq(buf)

        return m
