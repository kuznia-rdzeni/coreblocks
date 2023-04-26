from typing import Callable, Tuple, Optional
from amaranth import *
from amaranth.utils import *
from .core import *
from .core import SignalBundle, RecordDict
from ._utils import MethodLayout
from ..utils import ValueLike, assign, AssignType
from ..utils.fifo import BasicFifo

__all__ = [
    "FIFO",
    "MemoryBank",
    "Forwarder",
    "Collector",
    "ClickIn",
    "ClickOut",
    "AdapterTrans",
    "Adapter",
    "ConnectTrans",
    "ConnectAndTransformTrans",
    "CatTrans",
    "ManyToOneConnectTrans",
    "MethodTransformer",
    "MethodFilter",
    "MethodProduct",
    "Serializer",
]

# FIFOs

import amaranth.lib.fifo


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
        The read method. Accepts an empty argument, returns a `Record`.
    write: Method
        The write method. Accepts a `Record`, returns empty result.
    """

    def __init__(self, layout: MethodLayout, depth: int, fifo_type=amaranth.lib.fifo.SyncFIFO):
        """
        Parameters
        ----------
        layout: record layout
            The format of records stored in the FIFO.
        depth: int
            Size of the FIFO.
        fifoType: Elaboratable
            FIFO module conforming to Amaranth library FIFO interface. Defaults
            to SyncFIFO.
        """
        self.width = len(Record(layout))
        self.depth = depth
        self.fifoType = fifo_type

        self.read = Method(o=layout)
        self.write = Method(i=layout)

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = self.fifoType(width=self.width, depth=self.depth)

        assert fifo.fwft  # the read method requires FWFT behavior

        @def_method(m, self.write, ready=fifo.w_rdy)
        def _(arg):
            m.d.comb += fifo.w_en.eq(1)
            Method.comb += fifo.w_data.eq(arg)

        @def_method(m, self.read, ready=fifo.r_rdy)
        def _():
            m.d.comb += fifo.r_en.eq(1)
            return fifo.r_data

        return m


class MemoryBank(Elaboratable):
    """MemoryBank module.

    Provides a transactional interface to synchronous Amaranth Memory with one
    read port and one write port. It supports optionally writing with given granularity.

    Attributes
    ----------
    read_req: Method
        The read request method. Accepts an `addr` from which data should be read.
        Ready only if there is no response pending to be read or response is currently being read.
    read_resp: Method
        The read response method. Return `data_layout` Record which was saved on `addr` given by last
        `read_req` method call. Ready only after `read_req` call.
    write: Method
        The write method. Accepts `addr` where data should be saved, `data` in form of `data_layout`
        and optionaly `mask` if `granularity` is not None. `1` in mask means that apropriate part should be written.
    """
    def __init__(self, *, data_layout: MethodLayout, elem_count: int, granularity: Optional[int] = None):
        """
        Parameters
        ----------
        data_layout: record layout
            The format of records stored in the Memory.
        elem_count: int
            Number of elements stored in Memory.
        granularity: Optional[int]
            Granularity of write, forwarded to Amaranth. If `None` the whole record is always saved at once.
            If not the width of `data_layout` is split into `granularity` parts, which can be saved independently.
        """
        self.data_layout = data_layout
        self.elem_count = elem_count
        self.granularity = granularity
        self.width = len(Record(self.data_layout))
        self.addr_width = bits_for(self.elem_count - 1)

        self.read_req_layout = [("addr", self.addr_width)]
        if self.granularity is None:
            self.write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        else:
            self.write_layout = [
                ("addr", self.addr_width),
                ("data", self.data_layout),
                ("mask", self.width // self.granularity),
            ]

        self.read_req = Method(i=self.read_req_layout)
        self.read_resp = Method(o=self.data_layout)
        self.write = Method(i=self.write_layout)

        self.read_resp.schedule_before(self.read_req)

    def elaborate(self, platform) -> Module:
        m = Module()

        mem = Memory(width=self.width, depth=self.elem_count)
        m.submodules.read_port = read_port = mem.read_port()
        m.submodules.write_port = write_port = mem.write_port()
        read_output_valid = Signal()
        prev_read_addr = Signal(self.addr_width)
        m.d.comb += read_port.addr.eq(prev_read_addr)

        # read_resp has to be defined before read_req, to handle read_output_valid signal correctly
        @def_method(m, self.read_resp, ready=read_output_valid)
        def _():
            m.d.sync += read_output_valid.eq(0)
            return read_port.data

        @def_method(m, self.read_req, ready=~read_output_valid | self.read_resp.run)
        def _(addr):
            m.d.sync += read_output_valid.eq(1)
            m.d.comb += read_port.addr.eq(addr)
            m.d.sync += prev_read_addr.eq(addr)

        @def_method(m, self.write)
        def _(arg):
            m.d.comb += write_port.addr.eq(arg.addr)
            m.d.comb += write_port.data.eq(arg.data)
            if self.granularity is None:
                m.d.comb += write_port.en.eq(1)
            else:
                m.d.comb += write_port.en.eq(arg.mask)

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
        The read method. Accepts an empty argument, returns a `Record`.
    write: Method
        The write method. Accepts a `Record`, returns empty result.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: record layout
            The format of records forwarded.
        """
        self.read = Method(o=layout)
        self.write = Method(i=layout)
        self.clear = Method()
        self.head = Record.like(self.read.data_out)

        self.clear.add_conflict(self.read, Priority.LEFT)
        self.clear.add_conflict(self.write, Priority.LEFT)

    def elaborate(self, platform):
        m = Module()

        reg = Record.like(self.read.data_out)
        reg_valid = Signal()
        read_value = Record.like(self.read.data_out)
        m.d.comb += self.head.eq(read_value)

        self.write.schedule_before(self.read)  # to avoid combinational loops

        @def_method(m, self.write, ready=~reg_valid)
        def _(arg):
            Method.comb += read_value.eq(arg)  # for forwarding
            m.d.sync += reg.eq(arg)
            m.d.sync += reg_valid.eq(1)

        with m.If(reg_valid):
            m.d.comb += read_value.eq(reg)  # write method is not ready

        @def_method(m, self.read, ready=reg_valid | self.write.run)
        def _():
            m.d.sync += reg_valid.eq(0)
            return read_value

        @def_method(m, self.clear)
        def _():
            m.d.sync += reg_valid.eq(0)

        return m


# "Clicked" input


class ClickIn(Elaboratable):
    """Clicked input.

    Useful for interactive simulations or FPGA button/switch interfaces.
    On a rising edge (tested synchronously) of `btn`, the `get` method
    is enabled, which returns the data present on `dat` at the time.
    Inputs are synchronized.

    Attributes
    ----------
    get: Method
        The method for retrieving data from the input. Accepts an empty
        argument, returns a `Record`.
    btn: Signal, in
        The button input.
    dat: Record, in
        The data input.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: record layout
            The data format for the input.
        """
        self.get = Method(o=layout)
        self.btn = Signal()
        self.dat = Record(layout)

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        dat1 = Signal.like(self.dat)
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)
        m.d.sync += dat1.eq(self.dat)
        get_ready = Signal()
        get_data = Signal.like(self.dat)

        @def_method(m, self.get, ready=get_ready)
        def _():
            m.d.sync += get_ready.eq(0)
            return get_data

        with m.If(~btn2 & btn1):
            m.d.sync += get_ready.eq(1)
            m.d.sync += get_data.eq(dat1)

        return m


# "Clicked" output


class ClickOut(Elaboratable):
    """Clicked output.

    Useful for interactive simulations or FPGA button/LED interfaces.
    On a rising edge (tested synchronously) of `btn`, the `put` method
    is enabled, which, when called, changes the value of the `dat` signal.

    Attributes
    ----------
    put: Method
        The method for retrieving data from the input. Accepts a `Record`,
        returns empty result.
    btn: Signal, in
        The button input.
    dat: Record, out
        The data output.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: record layout
            The data format for the output.
        """
        self.put = Method(i=layout)
        self.btn = Signal()
        self.dat = Record(layout)

    def elaborate(self, platform):
        m = Module()

        btn1 = Signal()
        btn2 = Signal()
        m.d.sync += btn1.eq(self.btn)
        m.d.sync += btn2.eq(btn1)

        @def_method(m, self.put, ready=~btn2 & btn1)
        def _(arg):
            m.d.sync += self.dat.eq(arg)

        return m


# Testbench-friendly input/output


class AdapterBase(Elaboratable):
    data_in: Record
    data_out: Record

    def __init__(self, iface: Method):
        self.iface = iface
        self.en = Signal()
        self.done = Signal()

    def debug_signals(self) -> SignalBundle:
        return [self.en, self.done, self.data_in, self.data_out]


class AdapterTrans(AdapterBase):
    """Adapter transaction.

    Creates a transaction controlled by plain Amaranth signals. Allows to
    expose a method to plain Amaranth code, including testbenches.

    Attributes
    ----------
    en: Signal, in
        Activates the transaction (sets the `request` signal).
    done: Signal, out
        Signals that the transaction is performed (returns the `grant`
        signal).
    data_in: Record, in
        Data passed to the `iface` method.
    data_out: Record, out
        Data returned from the `iface` method.
    """

    def __init__(self, iface: Method):
        """
        Parameters
        ----------
        iface: Method
            The method to be called by the transaction.
        """
        super().__init__(iface)
        self.data_in = Record.like(iface.data_in)
        self.data_out = Record.like(iface.data_out)

    def elaborate(self, platform):
        m = Module()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        with Transaction().body(m, request=self.en):
            data_out = self.iface(m, data_in)
            Transaction.comb += self.data_out.eq(data_out)
            m.d.comb += self.done.eq(1)

        return m


class Adapter(AdapterBase):
    """Adapter method.

    Creates a method controlled by plain Amaranth signals. One of the
    possible uses is to mock a method in a testbench.

    Attributes
    ----------
    en: Signal, in
        Activates the method (sets the `ready` signal).
    done: Signal, out
        Signals that the method is called (returns the `run` signal).
    data_in: Record, in
        Data returned from the defined method.
    data_out: Record, out
        Data passed as argument to the defined method.
    """

    def __init__(self, *, i: MethodLayout = (), o: MethodLayout = ()):
        """
        Parameters
        ----------
        i: record layout
            The input layout of the defined method.
        o: record layout
            The output layout of the defined method.
        """
        super().__init__(Method(i=i, o=o))
        self.data_in = Record.like(self.iface.data_out)
        self.data_out = Record.like(self.iface.data_in)

    def elaborate(self, platform):
        m = Module()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        @def_method(m, self.iface, ready=self.en)
        def _(arg):
            Method.comb += self.data_out.eq(arg)
            m.d.comb += self.done.eq(1)
            return data_in

        return m


# Method combinators


class MethodTransformer(Elaboratable):
    """Method transformer.

    Takes a target method and creates a transformed method which calls the
    original target method, transforming the input and output values.
    The transformation functions take two parameters, a `Module` and the
    `Record` being transformed. Alternatively, a `Method` can be
    passed.

    Attributes
    ----------
    method: Method
        The transformed method.
    """

    def __init__(
        self,
        target: Method,
        *,
        i_transform: Optional[Tuple[MethodLayout, Callable[[Module, Record], RecordDict]]] = None,
        o_transform: Optional[Tuple[MethodLayout, Callable[[Module, Record], RecordDict]]] = None,
    ):
        """
        Parameters
        ----------
        target: Method
            The target method.
        i_transform: (record layout, function or Method), optional
            Input transformation. If specified, it should be a pair of a
            function and a input layout for the transformed method.
            If not present, input is not transformed.
        o_transform: (record layout, function or Method), optional
            Output transformation. If specified, it should be a pair of a
            function and a output layout for the transformed method.
            If not present, output is not transformed.
        """
        if i_transform is None:
            i_transform = (target.data_in.layout, lambda _, x: x)
        if o_transform is None:
            o_transform = (target.data_out.layout, lambda _, x: x)

        self.target = target
        self.method = Method(i=i_transform[0], o=o_transform[0])
        self.i_fun = i_transform[1]
        self.o_fun = o_transform[1]

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.method)
        def _(arg):
            return self.o_fun(m, self.target(m, self.i_fun(m, arg)))

        return m


class MethodFilter(Elaboratable):
    """Method filter.

    Takes a target method and creates a method which calls the target method
    only when some condition is true. The condition function takes two
    parameters, a module and the input `Record` of the method. Non-zero
    return value is interpreted as true. Alternatively to using a function,
    a `Method` can be passed as a condition.

    Caveat: because of the limitations of transaction scheduling, the target
    method is locked for usage even if it is not called.

    Attributes
    ----------
    method: Method
        The transformed method.
    """

    def __init__(
        self, target: Method, condition: Callable[[Module, Record], ValueLike], default: Optional[RecordDict] = None
    ):
        """
        Parameters
        ----------
        target: Method
            The target method.
        condition: function or Method
            The condition which, when true, allows the call to `target`. When
            false, `default` is returned.
        default: Value or dict, optional
            The default value returned from the filtered method when the condition
            is false. If omitted, zero is returned.
        """
        if default is None:
            default = Record.like(target.data_out)

        self.target = target
        self.method = Method.like(target)
        self.condition = condition
        self.default = default

    def elaborate(self, platform):
        m = Module()

        ret = Record.like(self.target.data_out)
        m.d.comb += assign(ret, self.default, fields=AssignType.ALL)

        @def_method(m, self.method)
        def _(arg):
            with m.If(self.condition(m, arg)):
                m.d.comb += ret.eq(self.target(m, arg))
            return ret

        return m


class MethodProduct(Elaboratable):
    def __init__(
        self,
        targets: list[Method],
        combiner: Optional[Tuple[MethodLayout, Callable[[Module, list[Record]], RecordDict]]] = None,
    ):
        """Method product.

        Takes arbitrary, non-zero number of target methods, and constructs
        a method which calls all of the target methods using the same
        argument. The return value of the resulting method is, by default,
        the return value of the first of the target methods. A combiner
        function can be passed, which can compute the return value from
        the results of every target method.

        Parameters
        ----------
        targets: list[Method]
            A list of methods to be called.
        combiner: (int or method layout, function), optional
            A pair of the output layout and the combiner function. The
            combiner function takes two parameters: a `Module` and
            a list of outputs of the target methods.

        Attributes
        ----------
        method: Method
            The product method.
        """
        if combiner is None:
            combiner = (targets[0].data_out.layout, lambda _, x: x[0])
        self.targets = targets
        self.combiner = combiner
        self.method = Method(i=targets[0].data_in.layout, o=combiner[0])

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.method)
        def _(arg):
            results = []
            for target in self.targets:
                results.append(target(m, arg))
            return self.combiner[1](m, results)

        return m


class Collector(Elaboratable):
    """Single result collector.

    Creates method that collects results of many methods with identical
    layouts. Each call of this method will return a single result of one
    of the provided methods.

    Attributes
    ----------
    method: Method
        Method which returns single result of provided methods.
    """

    def __init__(self, targets: list[Method]):
        """
        Parameters
        ----------
        method_list: list[Method]
            List of methods from which results will be collected.
        """
        self.method_list = targets
        layout = targets[0].data_out.layout
        self.method = Method(o=layout)

        for method in targets:
            if layout != method.data_out.layout:
                raise Exception("Not all methods have this same layout")

    def elaborate(self, platform):
        m = Module()

        m.submodules.forwarder = forwarder = Forwarder(self.method.data_out.layout)

        m.submodules.connect = ManyToOneConnectTrans(
            get_results=[get for get in self.method_list], put_result=forwarder.write
        )

        self.method.proxy(m, forwarder.read)

        return m


# Example transactions


class ConnectTrans(Elaboratable):
    """Simple connecting transaction.

    Takes two methods and creates a transaction which calls both of them.
    Result of the first method is connected to the argument of the second,
    and vice versa. Allows easily connecting methods with compatible
    layouts.
    """

    def __init__(self, method1: Method, method2: Method):
        """
        Parameters
        ----------
        method1: Method
            First method.
        method2: Method
            Second method.
        """
        self.method1 = method1
        self.method2 = method2

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            data1 = Record.like(self.method1.data_out)
            data2 = Record.like(self.method2.data_out)

            Transaction.comb += data1.eq(self.method1(m, data2))
            Transaction.comb += data2.eq(self.method2(m, data1))

        return m


class ConnectAndTransformTrans(Elaboratable):
    """Connecting transaction with transformations.

    Behaves like `ConnectTrans`, but modifies the transferred data using
    functions or `Method`s. Equivalent to a combination of
    `ConnectTrans` and `MethodTransformer`. The transformation
    functions take two parameters, a `Module` and the `Record` being
    transformed.
    """

    def __init__(
        self,
        method1: Method,
        method2: Method,
        *,
        i_fun: Optional[Callable[[Module, Record], RecordDict]] = None,
        o_fun: Optional[Callable[[Module, Record], RecordDict]] = None,
    ):
        """
        Parameters
        ----------
        method1: Method
            First method.
        method2: Method
            Second method, and the method being transformed.
        i_fun: function or Method, optional
            Input transformation (`method1` to `method2`).
        o_fun: function or Method, optional
            Output transformation (`method2` to `method1`).
        """
        self.method1 = method1
        self.method2 = method2
        self.i_fun = i_fun or (lambda _, x: x)
        self.o_fun = o_fun or (lambda _, x: x)

    def elaborate(self, platform):
        m = Module()

        m.submodules.transformer = transformer = MethodTransformer(
            self.method2,
            i_transform=(self.method1.data_out.layout, self.i_fun),
            o_transform=(self.method1.data_in.layout, self.o_fun),
        )
        m.submodules.connect = ConnectTrans(self.method1, transformer.method)

        return m


class ManyToOneConnectTrans(Elaboratable):
    """Many-to-one method connection.

    Connects each of a set of methods to another method using separate
    transactions. Equivalent to a set of `ConnectTrans`.
    """

    def __init__(self, *, get_results: list[Method], put_result: Method):
        """
        Parameters
        ----------
        get_results: list[Method]
            Methods to be connected to the `put_result` method.
        put_result: Method
            Common method for each of the connections created.
        """
        self.get_results = get_results
        self.m_put_result = put_result

        self.count = len(self.get_results)

    def elaborate(self, platform):
        m = Module()

        for i in range(self.count):
            m.submodules[f"ManyToOneConnectTrans_input_{i}"] = ConnectTrans(self.m_put_result, self.get_results[i])

        return m


class CatTrans(Elaboratable):
    """Concatenating transaction.

    Concatenates the results of two methods and passes the result to the
    third method.
    """

    def __init__(self, src1: Method, src2: Method, dst: Method):
        """
        Parameters
        ----------
        src1: Method
            First input method.
        src2: Method
            Second input method.
        dst: Method
            The method which receives the concatenation of the results of input
            methods.
        """
        self.src1 = src1
        self.src2 = src2
        self.dst = dst

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            sdata1 = self.src1(m)
            sdata2 = self.src2(m)
            ddata = Record.like(self.dst.data_in)
            self.dst(m, ddata)

            m.d.comb += ddata.eq(Cat(sdata1, sdata2))

        return m


class Serializer(Elaboratable):
    """Module to serialize request-response methods.

    Provides a transactional interface to connect many client `Module`\\s (which request somethig using method call)
    with a server `Module` which deliver method to request operation and method to get response.

    Requests are being serialized from many clients and forwarded to a server which can process only one request
    at the time. Responses from server are deserialized and passed to proper clients. `Serializer` assumes, that
    responses from the server are in-order, so the order of responses is the same as order of requests.


    Attributes
    ----------
    serialize_in: list[Method]
        List of request methods. Data layouts are the same as for `serialized_req_method`.
    serialize_out: list[Method]
        List of response methods. Data layouts are the same as for `serialized_resp_method`.
        `i`-th response method provides responses for requests from `i`-th `serialize_in` method.
    """
    def __init__(
        self,
        *,
        port_count: int,
        serialized_req_method: Method,
        serialized_resp_method: Method,
        depth: int = 4,
    ):
        """
        Parameters
        ----------
        port_count: int
            Number of ports, which should be generated. `len(serialize_in)=len(serialize_out)=port_count`
        serialized_req_method: Method
            Request method provided by server `Module`.
        serialized_resp_method: Method
            Response method provided by server `Module`.
        depth: Optional[int]
            Number of requests which can be forwarded to server, before server provides first response. Describe
            the resistance of `Serializer` to latency of server in case when server is fully pipelined.
        """
        self.port_count = port_count
        self.serialized_req_method = serialized_req_method
        self.serialized_resp_method = serialized_resp_method

        self.depth = depth

        self.id_layout = [("id", log2_int(self.port_count))]

        self.clear = Method()
        self.serialize_in = [Method.like(self.serialized_req_method) for _ in range(self.port_count)]
        self.serialize_out = [Method.like(self.serialized_resp_method) for _ in range(self.port_count)]

    def elaborate(self, platform) -> Module:
        m = Module()

        pending_requests = BasicFifo(self.id_layout, self.depth)
        m.submodules.pending_requests = pending_requests

        for i in range(self.port_count):

            @def_method(m, self.serialize_in[i])
            def _(arg):
                pending_requests.write(m, {"id": i})
                self.serialized_req_method(m, arg)

            @def_method(m, self.serialize_out[i], ready=(pending_requests.head.id == i))
            def _():
                pending_requests.read(m)
                return self.serialized_resp_method(m)

        self.clear.proxy(m, pending_requests.clear)

        return m
