from amaranth import *
from coreblocks.transactions import Method, def_method, ConflictPriority
from coreblocks.transactions._utils import _coerce_layout, MethodLayout
from typing import List


class BasicFifo(Elaboratable):
    def __init__(self, layout: MethodLayout, depth: int, *, init: List[int] = []) -> None:
        self.layout = _coerce_layout(layout)
        self.width = len(Record(self.layout))
        self.depth = depth
        # in this implementation, to allow concurrent Method access, memory needs to hold n+1 elements
        self.mem_depth = depth + 1

        self.read = Method(o=self.layout)
        self.write = Method(i=self.layout)
        self.clear = Method()

        if len(init) > depth:
            raise RuntimeError("Init list is longer than FIFO depth")

        self.buff = Memory(width=self.width, depth=self.mem_depth, init=init)

        self.write_ready = Signal()
        self.read_ready = Signal()

        self.read_idx = Signal((self.mem_depth - 1).bit_length())
        self.write_idx = Signal((self.mem_depth - 1).bit_length(), reset=len(init))

        self.clear.add_conflict(self.read, ConflictPriority.LEFT)
        self.clear.add_conflict(self.write, ConflictPriority.LEFT)

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.buff_rdport = self.buff_rdport = self.buff.read_port(
            domain="comb", transparent=True
        )  # FWFT behaviour
        m.submodules.buff_wrport = self.buff_wrport = self.buff.write_port()

        m.d.comb += self.read_ready.eq(self.read_idx != self.write_idx)
        m.d.comb += self.write_ready.eq(self.read_idx != ((self.write_idx + 1) % self.mem_depth))

        @def_method(m, self.write, ready=self.write_ready)
        def _(arg):
            m.d.comb += self.buff_wrport.addr.eq(self.write_idx)
            m.d.comb += self.buff_wrport.data.eq(arg)
            m.d.comb += self.buff_wrport.en.eq(1)

            m.d.sync += self.write_idx.eq((self.write_idx + 1) % self.mem_depth)

        @def_method(m, self.read, self.read_ready)
        def _(arg) -> Record:
            m.d.comb += self.buff_rdport.addr.eq(self.read_idx)

            m.d.sync += self.read_idx.eq((self.read_idx + 1) % self.mem_depth)

            return self.buff_rdport.data

        @def_method(m, self.clear)
        def _(arg):
            m.d.sync += self.read_idx.eq(0)
            m.d.sync += self.write_idx.eq(0)

        return m
