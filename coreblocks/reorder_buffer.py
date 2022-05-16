from . import transactions as ts
from .transactions import lib as tl
from amaranth import *


in_layout = [
    ("dst_reg", 5),
    ("phys_dst_reg", 8),
]

internal_layout = [
    ("dst_reg", 5),
    ("phys_dst_reg", 8),
    ("done", 1),
]


class ReorderBuffer(Elaboratable):
    def __init__(self) -> None:
        super().__init__()

        self.put = ts.Method(i=in_layout)
        self.mark_done = ts.Method(i=in_layout)
        self.retire = ts.Method(o=in_layout)
        self.data = Array(Record(internal_layout) for _ in range(128))

        self.cnt = Signal(7)

    def elaborate(self, platform) -> Module:
        m = Module()

        put_possible = self.cnt < 128

        retiring = Signal(1)

        output = Record(in_layout)

        with self.retire.body(m, ready=self.data[0].done, out=output):
            m.d.comb += output.eq(self.data[0])
            for i in range(127):
                m.d.sync += self.data[i].eq(self.data[i + 1])
            # m.d.sync += self.data[:-1].eq(self.data[1:])
            m.d.sync += self.cnt.eq(self.cnt - 1)
            m.d.comb += retiring.eq(1)

        with self.put.body(m, ready=put_possible & (retiring == 0)) as arg:
            m.d.sync += self.data[self.cnt].eq(arg)
            m.d.sync += self.cnt.eq(self.cnt + 1)

        with self.mark_done.body(m, ready=retiring == 0) as arg:
            for i in range(128):
                with m.If(self.data[i].dst_reg == arg.dst_reg):
                    m.d.sync += self.data[i].done.eq(1)

        return m
