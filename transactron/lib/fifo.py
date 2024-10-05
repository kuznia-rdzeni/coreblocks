from amaranth import *
import amaranth.lib.memory as memory
from transactron import Method, def_method, Priority, TModule
from transactron.utils._typing import ValueLike, MethodLayout, SrcLoc, MethodStruct
from transactron.utils.amaranth_ext import mod_incr
from transactron.utils.transactron_helpers import from_method_layout, get_src_loc


class BasicFifo(Elaboratable):
    """Transactional FIFO queue

    Attributes
    ----------
    read: Method
        Reads from the FIFO. Accepts an empty argument, returns a structure.
        Ready only if the FIFO is not empty.
    peek: Method
        Returns the element at the front (but not delete). Ready only if the FIFO
        is not empty. The method is nonexclusive.
    write: Method
        Writes to the FIFO. Accepts a structure, returns empty result.
        Ready only if the FIFO is not full.
    clear: Method
        Clears the FIFO entries. Has priority over `read` and `write` methods.
        Note that, clearing the FIFO doesn't reinitialize it to values passed in `init` parameter.

    """

    def __init__(self, layout: MethodLayout, depth: int, *, src_loc: int | SrcLoc = 0) -> None:
        """
        Parameters
        ----------
        layout: method layout
            Layout of data stored in the FIFO.
        depth: int
            Size of the FIFO.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.layout = layout
        self.width = from_method_layout(self.layout).size
        self.depth = depth

        src_loc = get_src_loc(src_loc)
        self.read = Method(o=self.layout, src_loc=src_loc)
        self.peek = Method(o=self.layout, nonexclusive=True, src_loc=src_loc)
        self.write = Method(i=self.layout, src_loc=src_loc)
        self.clear = Method(src_loc=src_loc)
        self.head = Signal(from_method_layout(layout))

        self.buff = memory.Memory(shape=self.width, depth=self.depth, init=[])

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

        m.submodules.buff = self.buff
        self.buff_wrport = self.buff.write_port()
        self.buff_rdport = self.buff.read_port(domain="sync", transparent_for=[self.buff_wrport])

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
        def _(arg: MethodStruct) -> None:
            m.d.top_comb += self.buff_wrport.addr.eq(self.write_idx)
            m.d.top_comb += self.buff_wrport.data.eq(arg)
            m.d.comb += self.buff_wrport.en.eq(1)

            m.d.sync += self.write_idx.eq(mod_incr(self.write_idx, self.depth))

        @def_method(m, self.read, self.read_ready)
        def _() -> ValueLike:
            m.d.sync += self.read_idx.eq(next_read_idx)
            return self.head

        @def_method(m, self.peek, self.read_ready)
        def _() -> ValueLike:
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
        self.count_next = Signal(self.max_count.bit_length())

        self.clear.add_conflict(self.acquire, Priority.LEFT)
        self.clear.add_conflict(self.release, Priority.LEFT)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.d.comb += self.release_ready.eq(self.count > 0)
        m.d.comb += self.acquire_ready.eq(self.count < self.max_count)

        with m.If(self.clear.run):
            m.d.comb += self.count_next.eq(0)
        with m.Else():
            m.d.comb += self.count_next.eq(self.count + self.acquire.run - self.release.run)

        m.d.sync += self.count.eq(self.count_next)

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
