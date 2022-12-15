from amaranth import *
from coreblocks.transactions import Method, def_method, ConflictPriority
from coreblocks.transactions._utils import _coerce_layout, MethodLayout
from typing import List, Optional


class BasicFifo(Elaboratable):
    """Transactional FIFO queue

    Attributes
    ----------
    read: Method
        Reads from the FIFO. Accepts an empty argument, returns a ``Record``.
        Ready only if the FIFO is not empty.
    write: Method
        Writes to the FIFO. Accepts a ``Record``, returns empty result.
        Ready only if the FIFO is not full.
    clear: Method
        Clears the FIFO entries. Has priority over ``read`` and ``write`` methods.
        Note that, clearing the FIFO doesn't reinitialize it to values passed in ``init`` parameter.

    """

    def __init__(self, layout: MethodLayout, depth: int, *, init: Optional[List[int]] = None) -> None:
        """
        Parameters
        ----------
        layout: Layout or int
            Layout of data stored in the FIFO.
            If integer is given, Record with field ``data`` and width of this paramter is used as internal layout.
        depth: int
            Size of the FIFO.
        init: List of int, optional
            List of memory elements to initialize FIFO at reset. List may be smaller than ``depth``.
            If ``Record`` is used as ``layout``, it has to be flattened to ``int`` first.
        """
        self.layout = _coerce_layout(layout)
        self.width = len(Record(self.layout))
        self.depth = depth

        self.read = Method(o=self.layout)
        self.write = Method(i=self.layout)
        self.clear = Method()

        if init is None:
            init = []

        if len(init) > depth:
            raise RuntimeError("Init list is longer than FIFO depth")

        self.buff = Memory(width=self.width, depth=self.depth, init=init)

        self.write_ready = Signal()
        self.read_ready = Signal()

        self.read_idx = Signal((self.depth - 1).bit_length())
        self.write_idx = Signal((self.depth - 1).bit_length(), reset=len(init))
        # current fifo depth
        self.level = Signal(range(self.depth), reset=len(init))

        self.clear.add_conflict(self.read, ConflictPriority.LEFT)
        self.clear.add_conflict(self.write, ConflictPriority.LEFT)

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.buff_rdport = self.buff_rdport = self.buff.read_port(
            domain="comb", transparent=True
        )  # FWFT behaviour
        m.submodules.buff_wrport = self.buff_wrport = self.buff.write_port()

        m.d.comb += self.read_ready.eq(self.level > 0)
        m.d.comb += self.write_ready.eq(self.level < self.depth)

        with m.If(self.read.run & ~self.write.run):
            m.d.sync += self.level.eq(self.level - 1)
        with m.If(self.write.run & ~self.read.run):
            m.d.sync += self.level.eq(self.level + 1)
        with m.If(self.clear.run):
            m.d.sync += self.level.eq(0)

        @def_method(m, self.write, ready=self.write_ready)
        def _(arg) -> None:
            m.d.comb += self.buff_wrport.addr.eq(self.write_idx)
            m.d.comb += self.buff_wrport.data.eq(arg)
            m.d.comb += self.buff_wrport.en.eq(1)

            m.d.sync += self.write_idx.eq((self.write_idx + 1) % self.depth)

        @def_method(m, self.read, self.read_ready)
        def _(arg) -> Record:
            m.d.comb += self.buff_rdport.addr.eq(self.read_idx)

            m.d.sync += self.read_idx.eq((self.read_idx + 1) % self.depth)

            return self.buff_rdport.data

        @def_method(m, self.clear)
        def _(arg) -> None:
            m.d.sync += self.read_idx.eq(0)
            m.d.sync += self.write_idx.eq(0)

        return m
