from amaranth import *
from coreblocks.transactions import Method, def_method, Priority, TModule, Transaction
from coreblocks.transactions._utils import MethodLayout
import coreblocks.transactions.lib as tlib
from coreblocks.utils._typing import ValueLike
from coreblocks.utils.utils import popcount, mod_incr


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

        self.clear.add_conflict(self.read, Priority.LEFT)
        self.clear.add_conflict(self.write, Priority.LEFT)

        # for interface compatibility with MultiportFifo
        self.read_methods = [self.read]
        self.write_methods = [self.write]

    def elaborate(self, platform):
        m = TModule()

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

        m.d.comb += self.buff_rdport.addr.eq(self.read_idx)
        m.d.comb += self.head.eq(self.buff_rdport.data)

        @def_method(m, self.write, ready=self.write_ready)
        def _(arg: Record) -> None:
            m.d.comb += self.buff_wrport.addr.eq(self.write_idx)
            m.d.comb += self.buff_wrport.data.eq(arg)
            m.d.comb += self.buff_wrport.en.eq(1)

            m.d.sync += self.write_idx.eq(mod_incr(self.write_idx, self.depth))

        @def_method(m, self.read, self.read_ready)
        def _() -> ValueLike:
            m.d.sync += self.read_idx.eq(mod_incr(self.read_idx, self.depth))
            return self.head

        @def_method(m, self.clear)
        def _() -> None:
            m.d.sync += self.read_idx.eq(0)
            m.d.sync += self.write_idx.eq(0)

        return m


class SortedMultiportFifo(Elaboratable):
    """Multiport fifo with methods called in order

    This class implements multiport fifo, it assumes that both read and write methods
    are called in order. So if the `i`-th method is being called and `j<i` then the user
    should also call the `j`-th method.

    If the above assumption is fulfilled, then the following properties hold:

    - If `x` has been written to fifo in cycle `i` and `y` in cycle `j` where `i<j`, then
      `k<=m` where `k` is the cycle in which `x` was read and `m` is the cycle in which `y` was read
    - The use of internal memory is balanced and optimal, so if only `n` first read/write methods is being
      active, then this means, that there are only `n` elements/free slots in the fifo. If there is more
      elements/free slots in the fifo than methods then all methods are active.

    WARNING: You probably don't want to use this class directly. See `MultiportFifo` instead.

    Attributes
    ----------
    read_methods : list[Method]
        List of methods to call in list order to read data from fifo.
    write_methods : list[Method]
        List of methods for writing data. The methods should be called in list order.
    clear : Method
        Clear the fifo.
    """

    def __init__(self, layout: MethodLayout, depth: int, port_count: int, fifo_count: int) -> None:
        """
        Parameters
        ----------
        layout : LayoutLike
            Layout of the data to be stored in the fifo
        depth : int
            Number of elements to store in the fifo. Must be divisible by `fifo_count`.
        fifo_count : int
            Number of internal fifos to store data in.
        port_count : int
            Number of read/write methods to create. Must be `ports_count <= fifo_count`.
        """
        self.layout = layout
        self.width = len(Record(self.layout))
        self.depth = depth
        self.port_count = port_count
        self.fifo_count = fifo_count

        self.connected_reads = 0
        self.connected_writes = 0

        self.read_methods = [Method(o=self.layout) for _ in range(self.port_count)]
        self.write_methods = [Method(i=self.layout) for _ in range(self.port_count)]
        self.clear = Method()

        self._selection_layout = [("valid", 1), ("data", self.layout)]

        if self.depth % self.fifo_count != 0:
            raise ValueError("MultiportFifo depth must be divisable by fifo_count")
        if self.fifo_count < self.port_count:
            raise ValueError("MultiportFifo requires fifo_count >= port_count")

        for method in self.read_methods:
            self.clear.add_conflict(method, Priority.LEFT)
        for method in self.write_methods:
            self.clear.add_conflict(method, Priority.LEFT)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        clear_signal = Signal()

        sub_fifo_depth = self.depth // self.fifo_count
        sub_fifos = [BasicFifo(self.layout, sub_fifo_depth) for i in range(self.fifo_count)]
        for i, sub_fifo in enumerate(sub_fifos):
            setattr(m.submodules, f"sub_fifo_{i}", sub_fifo)

        read_ready_list = [Signal() for _ in range(self.port_count)]
        read_grants = Signal(len(self.read_methods))
        read_grants_count = Signal.like(read_grants)
        read_outs = [Record(self.layout) for _ in self.read_methods]
        m.d.top_comb += read_grants.eq(Cat(method.run for method in self.read_methods))
        m.d.top_comb += read_grants_count.eq(popcount(read_grants))

        with m.FSM():
            for i in range(self.fifo_count):
                with m.State(f"current_read_{i}"):
                    for j in range(self.port_count):
                        selected_sub_fifo = sub_fifos[(i + j) % self.fifo_count]
                        m.d.comb += read_ready_list[j].eq(selected_sub_fifo.read.ready)
                        with Transaction().body(m, request=self.read_methods[j].run):
                            m.d.comb += read_outs[j].data.eq(selected_sub_fifo.read(m))
                    for j in range(self.port_count + 1):
                        with m.Switch(read_grants_count):
                            with m.Case(j):
                                m.next = f"current_read_{(i+j)%self.fifo_count}"
                    with m.If(clear_signal):
                        m.next = "current_read_0"

        for i in range(self.port_count):

            @def_method(m, self.read_methods[i], ready=read_ready_list[i])
            def _() -> ValueLike:
                return read_outs[i]

        write_ready_list = [Signal() for _ in range(self.port_count)]
        write_grants = Signal(len(self.write_methods), reset=0)
        write_grants_count = Signal.like(write_grants)
        write_ins = [Record(self.layout) for _ in self.write_methods]
        m.d.top_comb += write_grants.eq(Cat(method.run for method in self.write_methods))
        m.d.top_comb += write_grants_count.eq(popcount(write_grants))

        with m.FSM():
            for i in range(self.fifo_count):
                with m.State(f"current_write_{i}"):
                    for j in range(self.port_count):
                        selected_sub_fifo = sub_fifos[(i + j) % self.fifo_count]
                        m.d.comb += write_ready_list[j].eq(selected_sub_fifo.write.ready)
                        with Transaction().body(m, request=self.write_methods[j].run):
                            selected_sub_fifo.write(m, write_ins[j])
                    for j in range(self.port_count + 1):
                        with m.Switch(write_grants_count):
                            with m.Case(j):
                                m.next = f"current_write_{(i+j)%self.fifo_count}"
                    with m.If(clear_signal):
                        m.next = "current_write_0"

        for i in range(self.port_count):

            @def_method(m, self.write_methods[i], ready=write_ready_list[i])
            def _(arg: Record) -> None:
                m.d.comb += write_ins[i].eq(arg)

        @def_method(m, self.clear)
        def _():
            m.submodules.clear_product = clear_product = tlib.MethodProduct([sub_fifo.clear for sub_fifo in sub_fifos])
            clear_product.method(m)
            m.d.comb += clear_signal.eq(1)

        return m


class MultiportFifo(Elaboratable):
    """Multiport fifo

    Wrapper over SortedMultiportFifo that provides user friendly interface. Methods can be
    called in any order and calls will be correctly sorted and passed to SortedMultiportFifo.

    Attributes
    ----------
    read_methods : list[Method]
        List of read methods which can be called in any order.
    write_methods : list[Method]
        List of write methods which can be called in any order.
    clear : Method
        Proxy for the SortedMultiportFifo `clear` method.
    """

    def __init__(self, layout: MethodLayout, depth: int, port_count: int, fifo_count: int) -> None:
        """
        See: SortedMultiportFifo
        """
        self._internal_fifo = SortedMultiportFifo(layout, depth, port_count, fifo_count)
        self._read_proxy = tlib.PriorityOrderingProxyTrans(self._internal_fifo.read_methods)
        self._write_proxy = tlib.PriorityOrderingProxyTrans(self._internal_fifo.write_methods)

        self.read_methods = self._read_proxy.m_unordered
        self.write_methods = self._write_proxy.m_unordered
        self.clear = self._internal_fifo.clear

    def __getattr__(self, name):
        return getattr(self._internal_fifo, name)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.internal_fifo = self._internal_fifo
        m.submodules.read_proxy = self._read_proxy
        m.submodules.write_proxy = self._write_proxy

        return m
