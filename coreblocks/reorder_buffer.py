from cyclic_buffer import CyclicBuffer

from coreblocks.transactions import Method, Transaction

from itertools import tee

class MethodLayout:
    def __init__(self, _in, out):
        self._in = _in
        self.out = out

class ReorderBufferLayouts:
    def __init__(self):
        self.id_bits = 8 # TODO should be configurable

        # TODO can you make something like nested layouts in Amaranth?
        self.entry_layout = [
            ('entry_valid', 1)
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

        # TODO remove?
        # this was intended to be a building block for mark_done but I think
        # it can't be implemented efficiently (basically would need X values? resolved
        # at "compile" time?)
        #self.update = MethodLayout(
        #    _in = [('id', id_bits)] + entry_layout,
        #    out = []
        #)

        self.mark_done = MethodLayout(
          _in = [('id', id_bits)],
          out = []
        )


class ReorderBuffer(Elaboratable):
    """
    TODO fill me
    """
    def __init__(self, layouts: ReorderBufferLayouts):
        #* State
        size = 16 # TODO make configurable
        self.underlying = CyclicBuffer(size, layouts.entry_bits)

        #* methods
        self.put = method(layouts.put)
        self.discard_last = Method(layouts.discard_last)
        self.update = method(layouts.update)

        self.all_methods = [self.put, self.discard_last, self.update]

        for x in range(0, len(self.all_methods)):
            for y in range(x+1, len(self.all_methods)):
                x.add_conflict(y)

    def method(layout: MethodLayout):
        Method(i = layout._in, o = layout.out)

    def elaborate(self, platform):
        m = Module()

        put_out = Record(layout.put.out)
        discard_out = Record(layout.discard.out)

        with self.put.body(m, ready = underlying.insert_ready, out=put_out) as arg:
            m.d.comb += [
                underlying.insert_data.eq(arg.data),
                underlying.insert_start.eq(C(1)),
                put_out.id.eq(underlying.insert_id)
            ]

        with self.discard.body(m, ready=underlying.last_valid, out=discard_out) as arg:
            m.d.comb += [
                underlying.peek_id.eq(underlying.last_id),
                underlying.delete_last_start.eq(C(1)),
                discard_out.data.eq(underlying.peek_data)
            ]

        with self.mark_done.body(m, ready = C(1)) as arg:
            m.d.comb += [
                underlying.update_id.eq(arg.id)
                # TODO more
            ]

        return m
