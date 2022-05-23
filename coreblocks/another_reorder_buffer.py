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
            ('entry_valid', 1),
            ('entry_data', 7) # TODO split further
        ]

        #* methods
        self.put = MethodLayout(
            _in = entry_layout,
            out = [
                ('id', id_bits)
            ]
        )

        # ready only when the last element is valid
        self.discard = MethodLayout(
            _in = [],
            out = entry_layout
        )

        self.mark_done = MethodLayout(
          _in = [('id', id_bits)],
          out = []
        )


class ReorderBuffer(Elaboratable):
    """
    TODO fill me
    """
    def __init__(self, layouts: ReorderBufferLayouts):
        #* parmeters
        self.size = 16 # TODO make configurable
        self.last_allowed = self.size - 1

        #* state
        self.is_empty = Signal(init = 1)
        self.first = Signal(self.idWidth)
        self.last = Signal(self.idWidth)

        self.data = Memory(width = self.dataWidth, depth = self.size) # no init

        #* helpers
        self.next = Signal(self.idWidth)

        #* methods
        self.put = method(layouts.put)
        self.discard_last = Method(layouts.discard_last)
        self.update = method(layouts.update)

        self.all_methods = [self.put, self.discard_last, self.update]

        for x in range(0, len(self.all_methods)):
            for y in range(x+1, len(self.all_methods)):
                self.all_methods(x).add_conflict(self.all_methods(y))

    def method(layout: MethodLayout):
        Method(i = layout._in, o = layout.out)

    def elaborate(self, platform):
        m = Module()

        # TODO not sure why I need m.submodules but it came from example:
        # https://github.com/amaranth-lang/amaranth/blob/main/examples/basic/mem.py
        m.submodules.rdport = rdport = self.data.read_port()
        m.submodules.wrport = wrport = self.data.write_port()

        put_out = Record(layout.put.out)
        discard_out = Record(layout.discard.out)

        #* helpers

        m.d.comb += self.next.eq(Mux(self.last == self.last_allowed, 0, self.last + 1))

        #* methods implementations

        # uses: wrport
        with self.put.body(m, ready = self.is_empty | self.next != self.first, out=put_out) as arg:
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
        with self.discard.body(m, ready = self.last_valid & ~self.is_empty, out=discard_out) as arg:
            m.d.comb += [
                rdport.addr.eq(self.first),
                discard_out.data.eq(rdport.data)
            ]
            m.d.sync += [
                self.first.eq(Mux(self.first == self.last,
                                  self.first,
                                  Mux(self.first != self.last_allowed, self.first + 1, 0)
                                  )),
                self.is_empty.eq(self.first == self.last)
            ]

        # uses: rdport, wrport
        # TODO this readiness check is inaccurate: ideally it would check arguments
        # TODO this reads and writes at the same address, either:
        #   1. requires async read to perform in a single cycle (confirm)
        #   2. must be done in two cycles otherwise
        with self.mark_done.body(m, ready = ~self.is_empty) as arg:
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

        return m
