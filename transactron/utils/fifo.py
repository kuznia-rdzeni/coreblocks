from amaranth import *
from transactron import Method, def_method, Priority, TModule
from transactron._utils import MethodLayout
from transactron.utils._typing import ValueLike
from transactron.utils.utils import mod_incr


class BasicFifo(Elaboratable):
    """Transactional FIFO queue

    Attributes
    ----------
    read: Method
        Reads from the FIFO. Accepts an empty argument, returns a `Record`.
        Ready only if the FIFO is not empty.
    write: Method
        Writes to the FIFO. Accepts a `Record`, returns empty result.
        Ready only if the FIFO is not full.
    clear: Method
        Clears the FIFO entries. Has priority over `read` and `write` methods.
        Note that, clearing the FIFO doesn't reinitialize it to values passed in `init` parameter.

    """

    def __init__(self, layout: MethodLayout, depth: int) -> None:
        """
        Parameters
        ----------
        layout: record layout
            Layout of data stored in the FIFO.
            If integer is given, Record with field `data` and width of this paramter is used as internal layout.
        depth: int
            Size of the FIFO.

        """
        self.layout = layout
        self.width = len(Record(self.layout))
        self.depth = depth

        self.read = Method(o=self.layout)
        self.write = Method(i=self.layout)
        self.clear = Method()
        self.head = Record(self.layout)

        self.buff = Memory(width=self.width, depth=self.depth)

        self.write_ready = Signal()
        self.read_ready = Signal()

        self.read_idx = Signal((self.depth - 1).bit_length())
        self.write_idx = Signal((self.depth - 1).bit_length())
        # current fifo depth
        self.level = Signal((self.depth).bit_length())

        # for interface compatibility with MultiportFifo
        self.read_methods = [self.read]
        self.write_methods = [self.write]

    def elaborate(self, platform):
        m = TModule()

        next_read_idx = Signal.like(self.read_idx)
        m.d.comb += next_read_idx.eq(mod_incr(self.read_idx, self.depth))

        m.submodules.buff_rdport = self.buff_rdport = self.buff.read_port(domain="sync", transparent=True)
        m.submodules.buff_wrport = self.buff_wrport = self.buff.write_port()

        m.d.comb += self.read_ready.eq(self.level != 0)
        m.d.comb += self.write_ready.eq(self.level != self.depth)

        with m.If(self.read.run & ~self.write.run):
            m.d.sync += self.level.eq(self.level - 1)
        with m.If(self.write.run & ~self.read.run):
            m.d.sync += self.level.eq(self.level + 1)
        with m.If(self.clear.run):
            m.d.sync += self.level.eq(0)

        m.d.comb += self.buff_rdport.addr.eq(Mux(self.read.run, next_read_idx, self.read_idx))
        m.d.comb += self.head.eq(self.buff_rdport.data)

        @def_method(m, self.write, ready=self.write_ready)
        def _(arg: Record) -> None:
            m.d.top_comb += self.buff_wrport.addr.eq(self.write_idx)
            m.d.top_comb += self.buff_wrport.data.eq(arg)
            m.d.comb += self.buff_wrport.en.eq(1)

            m.d.sync += self.write_idx.eq(mod_incr(self.write_idx, self.depth))

        @def_method(m, self.read, self.read_ready)
        def _() -> ValueLike:
            m.d.sync += self.read_idx.eq(next_read_idx)
            return self.head

        @def_method(m, self.clear)
        def _() -> None:
            m.d.sync += self.read_idx.eq(0)
            m.d.sync += self.write_idx.eq(0)

        return m


class Semaphore(Elaboratable):
    """Semaphore"""

    def __init__(self, max_count: int) -> None:
        """
        Parameters
        ----------
        size: int
            Size of the semaphore.

        """
        self.max_count = max_count

        self.acquire = Method()
        self.release = Method()
        self.clear = Method()

        self.acquire_ready = Signal()
        self.release_ready = Signal()

        self.count = Signal(self.max_count.bit_length())

        self.clear.add_conflict(self.acquire, Priority.LEFT)
        self.clear.add_conflict(self.release, Priority.LEFT)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.d.comb += self.release_ready.eq(self.count > 0)
        m.d.comb += self.acquire_ready.eq(self.count < self.max_count)

        with m.If(self.clear.run):
            m.d.sync += self.count.eq(0)
        with m.Else():
            m.d.sync += self.count.eq(self.count + self.acquire.run - self.release.run)

        @def_method(m, self.acquire, ready=self.acquire_ready)
        def _() -> None:
            pass

        @def_method(m, self.release, ready=self.release_ready)
        def _() -> None:
            pass

        @def_method(m, self.clear)
        def _() -> None:
            pass

        return m
