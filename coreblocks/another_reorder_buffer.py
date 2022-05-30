from amaranth import *
from coreblocks.transactions import Method, Transaction

from itertools import tee

class MethodLayout:
    def __init__(self, _in, out):
        self._in = _in
        self.out = out

class ReorderBufferLayouts:
    def __init__(self):
        self.id_bits = 8 # TODO should be configurable (and match with implementation)

        # TODO can you make something like nested layouts in Amaranth?
        self.entry_layout = [
            ('entry_data', 8) # TODO split further
        ]

        #* methods
        self.put = MethodLayout(
            _in = self.entry_layout,
            out = [
                ('id', self.id_bits)
            ]
        )

        # ready only when the last element is valid
        self.discard = MethodLayout(
            _in = [],
            out = self.entry_layout
        )

        self.mark_done = MethodLayout(
          _in = [('id', self.id_bits)],
          out = []
        )

class Helpers():
    def method(layout: MethodLayout):
        return Method(i = layout._in, o = layout.out)


class ReorderBuffer(Elaboratable):
    """
    TODO fill me
    """
    def __init__(self, layouts: ReorderBufferLayouts):
        self.layouts = layouts
        #* parmeters
        self.size = 16 # TODO make configurable
        self.idWidth = layouts.id_bits # TODO make sure it matches with size
        self.last_allowed = self.size - 1
        self.dataWidth = sum([x[1] for x in layouts.entry_layout])

        #* state
        self.is_empty = Signal(reset = 1)
        self.first = Signal(self.idWidth)
        self.last = Signal(self.idWidth)
        self.first_valid = Signal()

        self.valid = Array(Signal() for _ in range(0, self.size))
        self.data = Memory(width = self.dataWidth, depth = self.size) # no init

        #* helpers
        self.next = Signal(self.idWidth)

        #* methods
        self.put = Helpers.method(layouts.put)
        self.discard = Helpers.method(layouts.discard)
        self.mark_done = Helpers.method(layouts.mark_done)

        self.all_methods = [self.put, self.discard, self.mark_done]

        for x in range(0, len(self.all_methods)):
            for y in range(x+1, len(self.all_methods)):
                self.all_methods[x].add_conflict(self.all_methods[y])

    def elaborate(self, platform):
        m = Module()

        # TODO not sure why I need m.submodules but it came from example:
        # https://github.com/amaranth-lang/amaranth/blob/main/examples/basic/mem.py
        m.submodules.rdport = rdport = self.data.read_port()
        m.submodules.wrport = wrport = self.data.write_port()

        put_out = Record(self.layouts.put.out)
        discard_out = Record(self.layouts.discard.out)

        #* helpers

        m.d.comb += self.next.eq(Mux(self.last == self.last_allowed, 0, self.last + 1))
        m.d.comb += self.first_valid.eq(not self.is_empty and self.valid[self.first])

        #* methods implementations

        # uses: wrport
        with self.put.body(m, ready = self.is_empty or (self.next != self.first), out=put_out) as arg:
            m.d.comb += [
                wrport.addr.eq(self.next),
                wrport.data.eq(Cat(arg.entry_valid, arg.entry_data)),
                wrport.en.eq(C(1))
            ]
            m.d.sync += [
                self.is_empty.eq(C(0)),
                self.last.eq(Mux(self.is_empty, self.last, self.next)),
                put_out.id.eq(self.next)
            ]

        # uses: rdport
        with self.discard.body(m, ready = self.first_valid and not self.is_empty, out=discard_out) as arg:
            m.d.comb += [
                rdport.addr.eq(self.first),
                discard_out.data.eq(rdport.data)
            ]
            m.d.sync += [
                self.first.eq(Mux(self.first == self.last,
                                  self.first,
                                  Mux(self.first != self.last_allowed, self.first + 1, 0)
                                  )),
                self.is_empty.eq(self.first == self.last),
                self.first_valid.eq(TODO) # TODO uh needs to read in the same cycle
            ]

        # uses: rdport, wrport
        # TODO this readiness check is inaccurate: ideally it would check arguments
        # TODO this reads and writes at the same address, either:
        #   1. requires async read to perform in a single cycle (confirm)
        #   2. must be done in two cycles otherwise
        with self.mark_done.body(m, ready = not self.is_empty) as arg:
            rdata_rec = Record(layouts.entry_layout)
            wdata_rec = Record(layouts.entry_layout)
            m.d.comb += [
                rdport.addr.eq(arg.id),
                wrport.addr.eq(arg.id),
                rdata_rec.eq(rwport.data),
                wdata_rec.eq(rwport.data),
                wdata_rec['entry_valid'].eq(C(1)), # TODO hopefully this overrides eq above
                                                   # (otherwise need intermediate record)
                wrport.en.eq(C(1)) # see TODO above
            ]
            m.d.sync += self.first_valid.eq(Mux(arg.id == TODO), TODO, TODO)

        return m
