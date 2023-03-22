from amaranth import *
from coreblocks.transactions import Method, def_method, Priority, TModule, Transaction
from amaranth.utils import log2_int
from coreblocks.transactions._utils import MethodLayout
from coreblocks.transactions.lib import MethodProduct, PriorityOrderingProxy
from coreblocks.utils._typing import ValueLike, ModuleLike
from coreblocks.utils.utils import popcount


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

    def get_read(self):
        """
        Return `read` method. This function is created for interface compatibility with MultiportFifo.
        """
        return self.read

    def get_write(self):
        """
        Return `write` method. This function is created for interface compatibility with MultiportFifo.
        """
        return self.write

    def elaborate(self, platform):
        def mod_incr(sig: Value, mod: int) -> Value:
            # perform (sig+1)%mod operation
            if mod == 2 ** len(sig):
                return sig + 1
            return Mux(sig == mod - 1, 0, sig + 1)

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


class MultiportFifo(Elaboratable):
    def __init__(self, layout: MethodLayout, depth: int, port_count: int, fifo_count: int) -> None:
        self.layout = layout
        self.width = len(Record(self.layout))
        self.depth = depth
        self.port_count = port_count
        self.fifo_count = fifo_count

        self.connected_reads = 0
        self.connected_writes = 0

        self._read_methods = [Method(o=self.layout) for _ in range(self.port_count)]
        self._write_methods = [Method(i=self.layout) for _ in range(self.port_count)]
        self.clear = Method()

        self._selection_layout = [("valid", 1), ("data", self.layout)]

        if self.depth % self.fifo_count != 0:
            raise ValueError("MultiportFifo depth must be divisable by fifo_count")
        if self.fifo_count < self.port_count:
            raise ValueError("MultiportFifo requires fifo_count >= port_count")

        for method in self._read_methods:
            self.clear.add_conflict(method, Priority.LEFT)
        for method in self._write_methods:
            self.clear.add_conflict(method, Priority.LEFT)

    def get_read(self):
        method = self._read_methods[self.connected_reads]
        self.connected_reads = (self.connected_reads + 1) % self.port_count
        return method

    def get_write(self):
        method = self._write_methods[self.connected_writes]
        self.connected_writes = (self.connected_writes + 1) % self.port_count
        return method

    def order(
        self, m: ModuleLike, to_order: Array, ready_ordering: Signal, data_direction_from_out: bool = True
    ) -> Array:
        """
        Put all ready elements from `to_order` to the begining of `out`
        """
        count = len(to_order)
        selected_counters = [Signal(range(count)) for _ in range(count + 1)]
        out = Array([Record(self._selection_layout) for _ in range(count)])

        for j in range(count):
            with m.If(ready_ordering[j]):
                m.d.comb += out[selected_counters[j]].valid.eq(1)
                if data_direction_from_out:
                    m.d.comb += to_order[j].eq(out[selected_counters[j]].data)
                else:
                    m.d.comb += out[selected_counters[j]].data.eq(to_order[j])
                m.d.comb += selected_counters[j + 1].eq(selected_counters[j] + 1)
        return out

    def elaborate(self, platform) -> TModule:
        m = TModule()

        clear_signal = Signal()

        sub_fifo_depth = self.depth // self.fifo_count
        sub_fifos = [BasicFifo(self.layout, sub_fifo_depth) for i in range(self.fifo_count)]
        for i, sub_fifo in enumerate(sub_fifos):
            setattr(m.submodules, f"sub_fifo_{i}", sub_fifo)

        read_ready_list = [Signal() for _ in range(self.port_count)]
        read_grants = Signal(len(self._read_methods))
        read_grants_count = popcount(m, read_grants)
        read_outs = [Record(self.layout) for _ in self._read_methods]
        ordered_read_outs = self.order(m, Array(read_outs), read_grants)
        ordered_read_ready = self.order(m, Array(read_ready_list), read_grants)

        with m.FSM():
            for i in range(self.fifo_count):
                with m.State(f"current_read_{i}"):
                    for j in range(self.port_count):
                        selected_sub_fifo = sub_fifos[(i + j) % self.fifo_count]
                        # m.d.comb += ordered_read_ready[j].eq(selected_sub_fifo.read.ready) <- should be
                        m.d.comb += read_ready_list[j].eq(selected_sub_fifo.read.ready)
                        with Transaction().body(m, request=ordered_read_outs[j].valid):
                            m.d.comb += ordered_read_outs[j].data.eq(selected_sub_fifo.read(m))
                    for j in range(self.port_count + 1):
                        with m.Switch(read_grants_count):
                            with m.Case(j):
                                name_of_next = f"current_read_{(i+j)%self.fifo_count}"
                                m.next = name_of_next
                    with m.If(clear_signal):
                        m.next = "current_read_0"

        for i in range(self.port_count):

            @def_method(m, self._read_methods[i], ready=read_ready_list[i])
            def _() -> ValueLike:
                m.d.comb += read_grants[i].eq(1)
                return read_outs[i]

        write_ready_list = [Signal() for _ in range(self.port_count)]
        write_granttts = Signal(len(self._write_methods), reset=0)
        write_granttts_count = popcount(m, write_granttts)
        write_ins = [Record(self.layout) for _ in self._write_methods]
        ordered_write_ins = self.order(m, Array(write_ins), write_granttts, data_direction_from_out=False)
        ordered_write_ready = self.order(m, Array(write_ready_list), write_granttts)

        write_start_state = "current_write_0"
        with m.FSM(write_start_state):
            for i in range(self.fifo_count):
                with m.State(f"current_write_{i}"):
                    for j in range(self.port_count):
                        selected_sub_fifo = sub_fifos[(i + j) % self.fifo_count]
                        # m.d.comb += ordered_write_ready[j].eq(selected_sub_fifo.write.ready) <- should be
                        m.d.comb += write_ready_list[j].eq(selected_sub_fifo.write.ready)
                        with Transaction().body(m, request=ordered_write_ins[j].valid):
                            selected_sub_fifo.write(m, ordered_write_ins[j].data)
                    for j in range(self.port_count + 1):
                        with m.Switch(write_granttts_count):
                            with m.Case(j):
                                m.next = f"current_write_{(i+j)%self.fifo_count}"
                    with m.If(clear_signal):
                        m.next = "current_write_0"

        for i in range(self.port_count):

            @def_method(m, self._write_methods[i], ready=write_ready_list[i])
            def _(data: Record) -> None:
                m.d.comb += write_granttts[i].eq(1)
                m.d.comb += write_ins[i].eq(data)

        @def_method(m, self.clear)
        def _():
            m.submodules.clear_product = clear_product = MethodProduct([sub_fifo.clear for sub_fifo in sub_fifos])
            clear_product.method(m)
            m.d.comb += clear_signal.eq(1)

        return m
