from amaranth import *
import amaranth.lib.fifo

from transactron.utils.transactron_helpers import from_method_layout
from ..core import *
from ..utils import SrcLoc, get_src_loc

__all__ = [
    "FIFO",
    "Forwarder",
    "Connect",
    "ConnectTrans",
    "ManyToOneConnectTrans",
]


class FIFO(Elaboratable):
    """FIFO module.

    Provides a transactional interface to Amaranth FIFOs. Exposes two methods:
    `read`, and `write`. Both methods are ready only when they can
    be executed -- i.e. the queue is respectively not empty / not full.
    It is possible to simultaneously read and write in a single clock cycle,
    but only if both readiness conditions are fulfilled.

    Attributes
    ----------
    read: Method
        The read method. Accepts an empty argument, returns a structure.
    write: Method
        The write method. Accepts a structure, returns empty result.
    """

    def __init__(
        self, layout: MethodLayout, depth: int, fifo_type=amaranth.lib.fifo.SyncFIFO, *, src_loc: int | SrcLoc = 0
    ):
        """
        Parameters
        ----------
        layout: method layout
            The format of structures stored in the FIFO.
        depth: int
            Size of the FIFO.
        fifoType: Elaboratable
            FIFO module conforming to Amaranth library FIFO interface. Defaults
            to SyncFIFO.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.width = from_method_layout(layout).size
        self.depth = depth
        self.fifoType = fifo_type

        src_loc = get_src_loc(src_loc)
        self.read = Method(o=layout, src_loc=src_loc)
        self.write = Method(i=layout, src_loc=src_loc)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fifo = fifo = self.fifoType(width=self.width, depth=self.depth)

        @def_method(m, self.write, ready=fifo.w_rdy)
        def _(arg):
            m.d.comb += fifo.w_en.eq(1)
            m.d.top_comb += fifo.w_data.eq(arg)

        @def_method(m, self.read, ready=fifo.r_rdy)
        def _():
            m.d.comb += fifo.r_en.eq(1)
            return fifo.r_data

        return m


# Forwarding with overflow buffering


class Forwarder(Elaboratable):
    """Forwarding with overflow buffering

    Provides a means to connect two transactions with forwarding. Exposes
    two methods: `read`, and `write`. When both of these methods are
    executed simultaneously, data is forwarded between them. If `write`
    is executed, but `read` is not, the value cannot be forwarded,
    but is stored into an overflow buffer. No further `write`\\s are
    possible until the overflow buffer is cleared by `read`.

    The `write` method is scheduled before `read`.

    Attributes
    ----------
    read: Method
        The read method. Accepts an empty argument, returns a structure.
    write: Method
        The write method. Accepts a structure, returns empty result.
    """

    def __init__(self, layout: MethodLayout, *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        layout: method layout
            The format of structures forwarded.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        src_loc = get_src_loc(src_loc)
        self.read = Method(o=layout, src_loc=src_loc)
        self.write = Method(i=layout, src_loc=src_loc)
        self.clear = Method(src_loc=src_loc)
        self.head = Signal.like(self.read.data_out)

        self.clear.add_conflict(self.read, Priority.LEFT)
        self.clear.add_conflict(self.write, Priority.LEFT)

    def elaborate(self, platform):
        m = TModule()

        reg = Signal.like(self.read.data_out)
        reg_valid = Signal()
        read_value = Signal.like(self.read.data_out)
        m.d.comb += self.head.eq(read_value)

        self.write.schedule_before(self.read)  # to avoid combinational loops

        @def_method(m, self.write, ready=~reg_valid)
        def _(arg):
            m.d.av_comb += read_value.eq(arg)  # for forwarding
            m.d.sync += reg.eq(arg)
            m.d.sync += reg_valid.eq(1)

        with m.If(reg_valid):
            m.d.av_comb += read_value.eq(reg)  # write method is not ready

        @def_method(m, self.read, ready=reg_valid | self.write.run)
        def _():
            m.d.sync += reg_valid.eq(0)
            return read_value

        @def_method(m, self.clear)
        def _():
            m.d.sync += reg_valid.eq(0)

        return m


class Connect(Elaboratable):
    """Forwarding by transaction simultaneity

    Provides a means to connect two transactions with forwarding
    by means of the transaction simultaneity mechanism. It provides
    two methods: `read`, and `write`, which always execute simultaneously.
    Typical use case is for moving data from `write` to `read`, but
    data flow in the reverse direction is also possible.

    Attributes
    ----------
    read: Method
        The read method. Accepts a (possibly empty) structure, returns
        a structure.
    write: Method
        The write method. Accepts a structure, returns a (possibly empty)
        structure.
    """

    def __init__(self, layout: MethodLayout = (), rev_layout: MethodLayout = (), *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        layout: method layout
            The format of structures forwarded.
        rev_layout: method layout
            The format of structures forwarded in the reverse direction.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        src_loc = get_src_loc(src_loc)
        self.read = Method(o=layout, i=rev_layout, src_loc=src_loc)
        self.write = Method(i=layout, o=rev_layout, src_loc=src_loc)

    def elaborate(self, platform):
        m = TModule()

        read_value = Signal.like(self.read.data_out)
        rev_read_value = Signal.like(self.write.data_out)

        self.write.simultaneous(self.read)

        @def_method(m, self.write)
        def _(arg):
            m.d.av_comb += read_value.eq(arg)
            return rev_read_value

        @def_method(m, self.read)
        def _(arg):
            m.d.av_comb += rev_read_value.eq(arg)
            return read_value

        return m


class ConnectTrans(Elaboratable):
    """Simple connecting transaction.

    Takes two methods and creates a transaction which calls both of them.
    Result of the first method is connected to the argument of the second,
    and vice versa. Allows easily connecting methods with compatible
    layouts.
    """

    def __init__(self, method1: Method, method2: Method, *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        method1: Method
            First method.
        method2: Method
            Second method.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.method1 = method1
        self.method2 = method2
        self.src_loc = get_src_loc(src_loc)

    def elaborate(self, platform):
        m = TModule()

        with Transaction(src_loc=self.src_loc).body(m):
            data1 = Signal.like(self.method1.data_out)
            data2 = Signal.like(self.method2.data_out)

            m.d.top_comb += data1.eq(self.method1(m, data2))
            m.d.top_comb += data2.eq(self.method2(m, data1))

        return m


class ManyToOneConnectTrans(Elaboratable):
    """Many-to-one method connection.

    Connects each of a set of methods to another method using separate
    transactions. Equivalent to a set of `ConnectTrans`.
    """

    def __init__(self, *, get_results: list[Method], put_result: Method, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        get_results: list[Method]
            Methods to be connected to the `put_result` method.
        put_result: Method
            Common method for each of the connections created.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.get_results = get_results
        self.m_put_result = put_result

        self.count = len(self.get_results)
        self.src_loc = get_src_loc(src_loc)

    def elaborate(self, platform):
        m = TModule()

        for i in range(self.count):
            m.submodules[f"ManyToOneConnectTrans_input_{i}"] = ConnectTrans(
                self.m_put_result, self.get_results[i], src_loc=self.src_loc
            )

        return m
