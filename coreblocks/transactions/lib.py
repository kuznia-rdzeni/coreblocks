import itertools
from contextlib import contextmanager
from typing import Callable, Tuple, Optional
from amaranth import *
from amaranth.utils import *
from .core import *
from .core import SignalBundle, RecordDict, TransactionBase
from ._utils import MethodLayout
from ..utils.fifo import BasicFifo
from ..utils import ValueLike, assign, AssignType, ModuleConnector, MultiPriorityEncoder
from ..utils.protocols import RoutingBlock
from ..utils._typing import LayoutLike

__all__ = [
    "FIFO",
    "MemoryBank",
    "Forwarder",
    "Connect",
    "Register",
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
    "MethodTryProduct",
    "condition",
    "connected_conditions",
    "condition_switch",
    "AnyToAnySimpleRoutingBlock",
    "OmegaRoutingNetwork",
    "PriorityOrderingTransProxyTrans",
    "PriorityOrderingProxyTrans",
    "RegisterPipe",
    "ShiftRegister",
    "MethodBrancherIn",
    "NotMethod",
    "DownCounter",
    "Barrier",
    "ContentAddressableMemory",
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
        m = TModule()

        m.submodules.fifo = fifo = self.fifoType(width=self.width, depth=self.depth)

        assert fifo.fwft  # the read method requires FWFT behavior

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
        m = TModule()

        reg = Record.like(self.read.data_out)
        reg_valid = Signal()
        read_value = Record.like(self.read.data_out)
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


class Register(Elaboratable):
    """
    This module implements a `Register`. It is a halfway between
    `Forwarder` and `2-FIFO`. In the `Register` data is always
    stored localy, so the critical path of the data is cut, but there is a
    combinational path between the control signals of the `read` and
    the `write` methods. For comparison:
    - in `Forwarder` there is both a data and a control combinational path
    - in `2-FIFO` there are no combinational paths

    The `read` method is scheduled before the `write`.

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
        m = TModule()

        reg = Record.like(self.read.data_out)
        reg_valid = Signal()
        m.d.top_comb += self.head.eq(reg)

        self.read.schedule_before(self.write)  # to avoid combinational loops

        @def_method(m, self.read, ready=reg_valid)
        def _():
            m.d.sync += reg_valid.eq(0)
            return reg

        @def_method(m, self.write, ready=~reg_valid | self.read.run)
        def _(arg):
            m.d.sync += reg.eq(arg)
            m.d.sync += reg_valid.eq(1)

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
        The read method. Accepts a (possibly empty) `Record`, returns
        a `Record`.
    write: Method
        The write method. Accepts a `Record`, returns a (possibly empty)
        `Record`.
    """

    def __init__(self, layout: MethodLayout = (), rev_layout: MethodLayout = ()):
        """
        Parameters
        ----------
        layout: record layout
            The format of records forwarded.
        rev_layout: record layout
            The format of records forwarded in the reverse direction.
        """
        self.read = Method(o=layout, i=rev_layout)
        self.write = Method(i=layout, o=rev_layout)

    def elaborate(self, platform):
        m = TModule()

        read_value = Record.like(self.read.data_out)
        rev_read_value = Record.like(self.write.data_out)

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
        m = TModule()

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
        m = TModule()

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
        m = TModule()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        with Transaction(name=f"AdapterTrans_{self.iface.name}").body(m, request=self.en):
            data_out = self.iface(m, data_in)
            m.d.top_comb += self.data_out.eq(data_out)
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

    def __init__(self, *, name: Optional[str] = None, i: MethodLayout = (), o: MethodLayout = ()):
        """
        Parameters
        ----------
        i: record layout
            The input layout of the defined method.
        o: record layout
            The output layout of the defined method.
        """
        super().__init__(Method(name=name, i=i, o=o))
        self.data_in = Record.like(self.iface.data_out)
        self.data_out = Record.like(self.iface.data_in)

    def elaborate(self, platform):
        m = TModule()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        @def_method(m, self.iface, ready=self.en)
        def _(arg):
            m.d.top_comb += self.data_out.eq(arg)
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
        i_transform: Optional[Tuple[MethodLayout, Callable[[TModule, Record], RecordDict]]] = None,
        o_transform: Optional[Tuple[MethodLayout, Callable[[TModule, Record], RecordDict]]] = None,
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
        m = TModule()

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
        self, target: Method, condition: Callable[[TModule, Record], ValueLike], default: Optional[RecordDict] = None
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
        m = TModule()

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
        combiner: Optional[Tuple[MethodLayout, Callable[[TModule, list[Record]], RecordDict]]] = None,
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
        m = TModule()

        @def_method(m, self.method)
        def _(arg):
            results = []
            for target in self.targets:
                results.append(target(m, arg))
            return self.combiner[1](m, results)

        return m


class MethodTryProduct(Elaboratable):
    def __init__(
        self,
        targets: list[Method],
        combiner: Optional[tuple[MethodLayout, Callable[[TModule, list[tuple[Value, Record]]], RecordDict]]] = None,
    ):
        """Method product with optional calling.

        Takes arbitrary, non-zero number of target methods, and constructs
        a method which tries to call all of the target methods using the same
        argument. The methods which are not ready are not called. The return
        value of the resulting method is, by default, empty. A combiner
        function can be passed, which can compute the return value from the
        results of every target method.

        Parameters
        ----------
        targets: list[Method]
            A list of methods to be called.
        combiner: (int or method layout, function), optional
            A pair of the output layout and the combiner function. The
            combiner function takes two parameters: a `Module` and
            a list of pairs. Each pair contains a bit which signals
            that a given call succeeded, and the result of the call.

        Attributes
        ----------
        method: Method
            The product method.
        """
        if combiner is None:
            combiner = ([], lambda _, __: {})
        self.targets = targets
        self.combiner = combiner
        self.method = Method(i=targets[0].data_in.layout, o=combiner[0])

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.method)
        def _(arg):
            results: list[tuple[Value, Record]] = []
            for target in self.targets:
                success = Signal()
                with Transaction().body(m):
                    m.d.comb += success.eq(1)
                    results.append((success, target(m, arg)))
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
        m = TModule()

        m.submodules.forwarder = forwarder = Forwarder(self.method.data_out.layout)

        m.submodules.connect = ManyToOneConnectTrans(
            get_results=[get for get in self.method_list], put_result=forwarder.write
        )

        self.method.proxy(m, forwarder.read)

        return m


# Example transactions


def connect_methods(m: TModule, method1: Method, method2: Method):
    data1 = Record.like(method1.data_out)
    data2 = Record.like(method2.data_out)

    m.d.top_comb += data1.eq(method1(m, data2))
    m.d.top_comb += data2.eq(method2(m, data1))


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
        m = TModule()

        with Transaction().body(m):
            connect_methods(m, self.method1, self.method2)
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
        i_fun: Optional[Callable[[TModule, Record], RecordDict]] = None,
        o_fun: Optional[Callable[[TModule, Record], RecordDict]] = None,
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
        m = TModule()

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
        m = TModule()

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
        m = TModule()

        with Transaction().body(m):
            sdata1 = self.src1(m)
            sdata2 = self.src2(m)
            ddata = Record.like(self.dst.data_in)
            self.dst(m, ddata)

            m.d.top_comb += assign(ddata, sdata1, fields = AssignType.ALL)
            m.d.top_comb += assign(ddata, sdata2, fields = AssignType.ALL)

        return m


class ArgumentsToResultsZipper(Elaboratable):
    """Zips arguments used to call method with results, cutting critical path.

    This module provides possibility to pass arguments from caller and connect it with results
    from callee. Arguments are stored in 2-FIFO and results in Forwarder. Because of this asymmetry,
    the callee should provide results as long as they aren't correctly received.

    FIFO is used as rate-limiter, so when FIFO reaches full capacity there should be no new requests issued.

    Example topology:

    ```{mermaid}
    graph LR
        Caller;
        Caller -- write_arguments --> 2-FIFO;
        Caller -- invoke --> Callee["Callee \n (1+ cycle delay)"];
        Callee -- write_results --> Forwarder;
        Forwarder -- read --> Zip;
        2-FIFO -- read --> Zip;
        Zip -- read --> User;

        subgraph ArgumentsToResultsZipper
            Forwarder;
            2-FIFO;
            Zip;
        end
    ```

    Attributes
    ----------
    write_args: Method
        Method to write arguments with `args_layout` format to 2-FIFO.
    write_results: Method
        Method to save results with `results_layout` in the Forwarder.
    read: Method
        Reads latest entries from the fifo and the forwarder and return them as
        record with two fields: 'args' and 'results'.
    """

    def __init__(self, args_layout: MethodLayout, results_layout: MethodLayout):
        """
        Parameters
        ----------
        args_layout: record layout
            The format of arguments.
        results_layout: record layout
            The format of results.
        """
        self.results_layout = results_layout
        self.args_layout = args_layout
        self.output_layout = [("args", self.args_layout), ("results", results_layout)]

        self.write_args = Method(i=self.args_layout)
        self.write_results = Method(i=self.results_layout)
        self.read = Method(o=self.output_layout)

    def elaborate(self, platform):
        m = TModule()

        fifo = FIFO(self.args_layout, depth=2)
        forwarder = Forwarder(self.results_layout)

        m.submodules.fifo = fifo
        m.submodules.forwarder = forwarder

        @def_method(m, self.write_args)
        def _(arg):
            fifo.write(m, arg)

        @def_method(m, self.write_results)
        def _(arg):
            forwarder.write(m, arg)

        @def_method(m, self.read)
        def _():
            args = fifo.read(m)
            results = forwarder.read(m)
            return {"args": args, "results": results}

        return m


class MemoryBank(Elaboratable):
    """MemoryBank module.

    Provides a transactional interface to synchronous Amaranth Memory with one
    read and one write port. It supports optionally writing with given granularity.

    Reads aren't transparent.

    Attributes
    ----------
    read_req: Method
        The read request method. Accepts an `addr` from which data should be read.
        Only ready if there is there is a place to buffer response.
    read_resp: Method
        The read response method. Return `data_layout` Record which was saved on `addr` given by last
        `read_req` method call. Only ready after `read_req` call.
    write: Method
        The write method. Accepts `addr` where data should be saved, `data` in form of `data_layout`
        and optionally `mask` if `granularity` is not None. `1` in mask means that appropriate part should be written.
    """

    def __init__(
        self, *, data_layout: MethodLayout, elem_count: int, granularity: Optional[int] = None, safe_writes: bool = True
    ):
        """
        Parameters
        ----------
        data_layout: record layout
            The format of records stored in the Memory.
        elem_count: int
            Number of elements stored in Memory.
        granularity: Optional[int]
            Granularity of write, forwarded to Amaranth. If `None` the whole record is always saved at once.
            If not, the width of `data_layout` is split into `granularity` parts, which can be saved independently.
        safe_writes: bool
            Set to `False` if an optimisation can be done to increase throughput of writes. This will cause that
            writes will be reordered with respect to reads eg. in sequence "read A, write A X", read can return
            "X" even when write was called later. By default `True`, which disable optimisation.
        """
        self.data_layout = data_layout
        self.elem_count = elem_count
        self.granularity = granularity
        self.width = len(Record(self.data_layout))
        self.addr_width = log2_int(self.elem_count, False)
        self.safe_writes = safe_writes

        self.read_req_layout = [("addr", self.addr_width)]
        self.write_layout = [("addr", self.addr_width), ("data", self.data_layout)]
        if self.granularity is not None:
            self.write_layout.append(("mask", self.width // self.granularity))

        self.read_req = Method(i=self.read_req_layout)
        self.read_resp = Method(o=self.data_layout)
        self.write = Method(i=self.write_layout)
        self._internal_read_resp_trans = None

    def elaborate(self, platform) -> TModule:
        m = TModule()

        mem = Memory(width=self.width, depth=self.elem_count)
        m.submodules.read_port = read_port = mem.read_port()
        m.submodules.write_port = write_port = mem.write_port(granularity=self.granularity)
        read_output_valid = Signal()
        prev_read_addr = Signal(self.addr_width)
        write_pending = Signal()
        write_req = Signal()
        write_args = Record(self.write_layout)
        write_args_prev = Record(self.write_layout)
        m.d.comb += read_port.addr.eq(prev_read_addr)

        zipper = ArgumentsToResultsZipper([("valid", 1)], self.data_layout)
        m.submodules.zipper = zipper

        self._internal_read_resp_trans = Transaction()
        with self._internal_read_resp_trans.body(m, request=read_output_valid):
            m.d.sync += read_output_valid.eq(0)
            zipper.write_results(m, read_port.data)

        write_trans = Transaction()
        with write_trans.body(m, request=write_req | (~read_output_valid & write_pending)):
            if self.safe_writes:
                with m.If(write_pending):
                    m.d.comb += assign(write_args, write_args_prev, fields=AssignType.ALL)
            m.d.sync += write_pending.eq(0)
            m.d.comb += write_port.addr.eq(write_args.addr)
            m.d.comb += write_port.data.eq(write_args.data)
            if self.granularity is None:
                m.d.comb += write_port.en.eq(1)
            else:
                m.d.comb += write_port.en.eq(write_args.mask)

        @def_method(m, self.read_resp)
        def _():
            output = zipper.read(m)
            return output.results

        @def_method(m, self.read_req, ~write_pending)
        def _(addr):
            m.d.sync += read_output_valid.eq(1)
            m.d.comb += read_port.addr.eq(addr)
            m.d.sync += prev_read_addr.eq(addr)
            zipper.write_args(m, valid=1)

        @def_method(m, self.write, ~write_pending)
        def _(arg):
            if self.safe_writes:
                with m.If((arg.addr == read_port.addr) & (read_output_valid | self.read_req.run)):
                    m.d.sync += write_pending.eq(1)
                    m.d.sync += assign(write_args_prev, arg, fields=AssignType.ALL)
                with m.Else():
                    m.d.comb += write_req.eq(1)
            else:
                m.d.comb += write_req.eq(1)
            m.d.comb += assign(write_args, arg, fields=AssignType.ALL)

        return m


class Serializer(Elaboratable):
    """Module to serialize request-response methods.

    Provides a transactional interface to connect many client `Module`\\s (which request somethig using method call)
    with a server `Module` which provides method to request operation and method to get response.

    Requests are being serialized from many clients and forwarded to a server which can process only one request
    at the time. Responses from server are deserialized and passed to proper client. `Serializer` assumes, that
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
            Request method provided by server's `Module`.
        serialized_resp_method: Method
            Response method provided by server's `Module`.
        depth: int
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

    def elaborate(self, platform) -> TModule:
        m = TModule()

        pending_requests = BasicFifo(self.id_layout, self.depth)
        m.submodules.pending_requests = pending_requests

        @loop_def_method(m, self.serialize_in)
        def _(i, arg):
            pending_requests.write(m, {"id": i})
            self.serialized_req_method(m, arg)

        @loop_def_method(m, self.serialize_out, ready_list=lambda i: pending_requests.head.id == i)
        def _(_, arg):
            pending_requests.read(m)
            return self.serialized_resp_method(m, arg)

        self.clear.proxy(m, pending_requests.clear)

        return m


# Conditions using simultaneous transactions


@contextmanager
def condition(m: TModule, *, nonblocking: bool = True, priority: bool = True):
    """Conditions using simultaneous transactions.

    This context manager allows to easily define conditions utilizing
    nested transactions and the simultaneous transactions mechanism.
    It is similar to Amaranth's `If`, but allows to call different and
    possibly overlapping method sets in each branch. Each of the branches is
    defined using a separate nested transaction.

    Inside the condition body, branches can be added, which are guarded
    by Boolean conditions. A branch is considered for execution if its
    condition is true and the called methods can be run. A catch-all,
    default branch can be added, which can be executed only if none of
    the other branches execute. Note that the default branch can run
    even if some of the conditions are true, but their branches can't
    execute for other reasons.

    Parameters
    ----------
    m : TModule
        A module where the condition is defined.
    nonblocking : bool
        States that the condition should not block the containing method
        or transaction from running, even when every branch cannot run.
        If `nonblocking` is false and every branch cannot run (because of
        a false condition or disabled called methods), the whole method
        or transaction will be stopped from running.
    priority : bool
        States that the conditions are not mutually exclusive and should
        be tested in order. This influences the scheduling order of generated
        transactions.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        with condition(m) as branch:
            with branch(cond1):
                ...
            with branch(cond2):
                ...
            with branch():  # default, optional
                ...
    """
    this = TransactionBase.get()
    transactions = list[Transaction]()
    last = False

    @contextmanager
    def branch(cond: Optional[ValueLike] = None):
        nonlocal last
        if last:
            raise RuntimeError("Condition clause added after catch-all")
        req = cond if cond is not None else 1
        name = f"{this.name}_cond{len(transactions)}"
        with (transaction := Transaction(name=name)).body(m, request=req):
            yield
        if transactions and priority:
            transactions[-1].schedule_before(transaction)
        if cond is None:
            last = True
            if not priority:
                for transaction0 in transactions:
                    transaction0.schedule_before(transaction)
        transactions.append(transaction)

    yield branch

    if nonblocking and not last:
        with branch():
            pass

    this.simultaneous_alternatives(*transactions)


def condition_switch(
    m: TModule, variable: Signal, branch_number: int, *, nonblocking: bool = False, priority: bool = False
):
    """
    Syntax sugar to easy define condition which compares given signal to first `branch_number` integers.
    """
    with condition(m, nonblocking=nonblocking, priority=priority) as branch:
        for i in range(branch_number):
            with branch(variable == i):
                yield i

@contextmanager
def connected_conditions(m : TModule, *, nonblocking = False):
    """
    All conditions for which branch is True has to execute simultanuesly.

    This is a wrapper over `connection` that allows to define set of condtions in a transaction such that:
        - all conditions with a minimum one branch evaluated to `True` have to execute
        (if they can not because e.g. method is not ready then all conditions stalls)
        - if there is a branch which evaluated to True, transaction will be ready
            all conditions whith all barnches evaluated to False will be ignored
        - if nonblocking=False and there is no branch evaluated to `True` in any condition
        then transaction is not ready
    """
    priority = False # hardcoded till issue #436 will be closed
    all_not_conds_list = []
    @contextmanager
    def _internal_condition():
        condition_conds = []
        true_branch_f = None
        @contextmanager
        def _internal_branch(cond: ValueLike):
            condition_conds.append(cond)
            assert true_branch_f is not None
            with true_branch_f(cond):
                yield
        with condition(m, nonblocking = False, priority = priority) as branch:
            true_branch_f = branch
            yield _internal_branch

            not_conds = Signal()
            m.d.top_comb += not_conds.eq(~Cat(condition_conds).any())
            all_not_conds_list.append(not_conds)
            with branch(not_conds):
                pass

    all_conds = Signal()
    with condition(m, nonblocking = False) as branch:
        with branch(all_conds):
            yield _internal_condition

    if nonblocking:
        m.d.top_comb += all_conds.eq(1)
    else:
        m.d.top_comb += all_conds.eq(~Cat(all_not_conds_list).all())


def def_one_caller_wrapper(method_to_wrap: Method, wrapper: Method) -> TModule:
    """
    Function used to a wrap method that can only have one caller. After wrapping
    many callers can call the wrapper. Results are buffered and passed to the
    wrapped method from one source.

    Parameters
    ----------
    method_to_wrap : Method
        Method that can only be called by a single caller.
    wrapper : Method
        Method to be defined as a wrapper over `method_to_wrap`.

    Returns
    -------
    TModule
        Module with created amaranth connections.
    """
    if len(method_to_wrap.data_out):
        raise ValueError("def_one_caller_wrapper support only wrapping of methods which don't return data.")

    m = TModule()
    buffer = FIFO(method_to_wrap.data_in.layout, 2)
    m.submodules += buffer

    @def_method(m, wrapper)
    def _(arg):
        buffer.write(m, arg)

    m.submodules += ConnectTrans(buffer.read, method_to_wrap)

    return m


class AnyToAnySimpleRoutingBlock(Elaboratable, RoutingBlock):
    """Routing by any-to-any connections

    Routing block which create a any-to-any connection between inputs and
    outputs and next forwards input data to proper output based on address.

    - Connection complexity: O(n^2)
    - All connections are combinational
    - Routing is done based on an address, so to don't have combinational loop
      there is a buffering of inputs on each send method

    Attributes
    ----------
    send : list[Method]
        List of methods used to send `data` to the receiver with `addr`.
    receive : list[Method]
        Methods used to receive data based on addresses. k-th method
        from the list returns data for address `k`.
    """

    def __init__(self, inputs_count: int, outputs_count: int, data_layout: LayoutLike):
        """
        Parameters
        ----------
        outputs_count: int
            Number of receiver methods which should be generated.
        data_layout: LayoutLike
            Layout of data which should be transferend from sender to reciver.
        """
        self.inputs_count = inputs_count
        self.outputs_count = outputs_count
        self.data_layout = data_layout
        self.addr_width = bits_for(self.outputs_count - 1)

        self.send_layout: LayoutLike = [("addr", self.addr_width), ("data", self.data_layout)]

        self.send = [Method(i=self.send_layout) for _ in range(self.inputs_count)]
        self.receive = [Method(o=self.data_layout) for _ in range(self.outputs_count)]

        self._connectors = [Connect(self.data_layout) for _ in range(self.outputs_count)]

    def elaborate(self, platform):
        if not self.send:
            raise ValueError("Sender lists empty")
        m = TModule()

        m.submodules.connectors = ModuleConnector(*self._connectors)

        _internal_send = [Method(i=self.send_layout) for _ in range(self.inputs_count)]

        @loop_def_method(m, _internal_send)
        def _(i, addr, data):
            with condition(m, nonblocking=False) as branch:
                for i in range(self.outputs_count):
                    with branch(addr == i):
                        self._connectors[i].write(m, data)

        sender_wrappers = [def_one_caller_wrapper(_internal_send[i], self.send[i]) for i in range(self.inputs_count)]
        m.submodules.sender_wrappers = ModuleConnector(*sender_wrappers)

        for i in range(self.outputs_count):
            self.receive[i].proxy(m, self._connectors[i].read)

        return m


class _OmegaRoutingSwitch(Elaboratable):
    """An internal building block of OmegaRoutingNetwork

    This switch has `_ports_count=2` inputs and outputs and based
    on the most significant bit of the address it routes data either
    to the upper (if MSB = 0) or the lower (MSB = 1) output.

    The output address is shifted 1 bit to the left, so that the bit, based on which
    this switch was routing, is removed and the original second MSB bit
    is now the MSB.

    Attributes
    ----------
    _ports_count : int
        Implementation defined constant to describe the number of input and output ports.
    reads : list[Method], len(reads) == _ports_count
        Methods used to read data from upper output (0-th method) and
        lower output (1-st method)
    writes : list[Method], len(writes) == _ports_count
        Methods used to insert data into the switch.
    """

    _ports_count = 2

    def __init__(self, send_layout: LayoutLike):
        """
        Parameters
        ----------
        send_layout : LayoutLike
            Layout with two fields: `addr` and `data`.
        """
        self.send_layout = send_layout

        # 0 - "up" port; 1 - "down" port
        self.reads = [Method(o=self.send_layout) for _ in range(self._ports_count)]
        self.writes = [Method(i=self.send_layout) for _ in range(self._ports_count)]

    def elaborate(self, platform):
        m = TModule()

        buffers = [FIFO(self.send_layout, 2) for _ in range(self._ports_count)]
        m.submodules.buffers = ModuleConnector(*buffers)

        @loop_def_method(m, self.writes)
        def _(_, addr, data):
            new_addr = addr << 1
            with m.If(addr[-1]):
                buffers[0].write(m, addr=new_addr, data=data)
            with m.Else():
                buffers[1].write(m, addr=new_addr, data=data)

        for i in range(self._ports_count):
            self.reads[i].proxy(m, buffers[i].read)
        return m


class OmegaRoutingNetwork(Elaboratable, RoutingBlock):
    """Omega routing network

    A network consisting of grid of small switches, each of which routes data either
    "up" or "down", based on one bit of the address. Connecting switches in the correct
    way allows us to construct a routing network with log(n) depth.

    Currently, the implementation supports only power of two number of ports.

    Attributes
    ----------
    send : list[Method]
        List of methods used to send `data` to the receiver with `addr`.
    receive : list[Method]
        Methods used to receive data based on addresses. k-th method
        from the list returns data for address `k`.
    """

    def __init__(self, ports_count: int, data_layout: LayoutLike):
        """
        Parameters
        ----------
        ports_count : int
            The number of input and output ports to create.
        data_layout : LayoutLike
            Layout of data which are being transfered by network.
        """
        self.outputs_count = ports_count
        self.data_layout = data_layout

        self.addr_width = self.stages = bits_for(self.outputs_count - 1)
        self.switch_port_count = _OmegaRoutingSwitch._ports_count
        self.switches_in_stage = self.outputs_count // self.switch_port_count

        if self.outputs_count.bit_count() > 1:
            raise ValueError("OmegaRoutingNetwork don't support odd number of outputs.")

        self.send_layout: LayoutLike = [("addr", self.addr_width), ("data", self.data_layout)]

        self.send = [Method(i=self.send_layout) for _ in range(self.outputs_count)]
        self.receive = [Method(o=self.data_layout) for _ in range(self.outputs_count)]

    def _connect_stages(
        self, from_stage: list[_OmegaRoutingSwitch], to_stage: list[_OmegaRoutingSwitch]
    ) -> Elaboratable:
        # flatten list in format 00112233
        froms = []
        for switch in from_stage:
            froms += switch.reads

        # flatten list in format 01230123
        tos = []
        for i in range(self.switch_port_count):
            for switch in to_stage:
                tos.append(switch.writes[i])

        assert len(froms) == len(tos)
        connections = [ConnectTrans(froms[i], tos[i]) for i in range(len(froms))]
        return ModuleConnector(*connections)

    def elaborate(self, platform):
        m = TModule()

        _internal_send = [Method(i=self.send_layout) for _ in range(self.outputs_count)]

        switches: list[list[_OmegaRoutingSwitch]] = []
        switches_connectors = []
        for i in range(self.stages):
            switches.append([_OmegaRoutingSwitch(self.send_layout) for _ in range(self.switches_in_stage)])
            switches_connectors.append(ModuleConnector(*switches[i]))
        m.submodules.switches = ModuleConnector(*switches_connectors)

        stages_connectors = []
        for i in range(1, self.stages):
            stages_connectors.append(self._connect_stages(switches[i - 1], switches[i]))
        m.submodules.stages_connectors = ModuleConnector(*stages_connectors)

        @loop_def_method(m, _internal_send)
        def _(i: int, arg):
            switches[0][i // self.switch_port_count].writes[i % self.switch_port_count](m, arg)

        sender_wrappers = [def_one_caller_wrapper(_internal_send[i], self.send[i]) for i in range(self.outputs_count)]
        m.submodules.sender_wrappers = ModuleConnector(*sender_wrappers)

        @loop_def_method(m, self.receive)
        def _(i: int):
            i = self.outputs_count - i - 1
            return {"data": (switches[-1][i // self.switch_port_count].reads[i % self.switch_port_count](m)).data}

        return m


class PriorityOrderingTransProxyTrans(Elaboratable):
    """Proxy for ordering methods

    This proxy allows to order called methods. It guarantee that if
    there is a `k` method called (in any order), then they will be
    connected to `k` first methods from ordered list and both arguments
    and results of methods will be correctly forwarded.

    There is no fairness algorithm used, but there is a guarantee that always
    the biggest subset of available methods will be called.

    WARNING: This scales up badly -- O(2^n) -- so it is discouraged to use
    that module with more than 6 inputs.
    """

    def __init__(self, methods_ordered: list[Method], methods_unordered: list[Method]):
        """
        Parameters
        ----------
        methods_ordered : list[Method]
            A list of methods which will be called in order. So if `j`-th method
            is called and `i<j` then `i`-th Method also is called.
        methods_unordered : list[Method]
            Methods whose calls should be ordered.
        """
        self._m_ordered = methods_ordered
        self._m_unordered = methods_unordered

    def elaborate(self, platform):
        m = TModule()

        with Transaction().body(m):
            with condition(m, priority=True) as branch:
                for k in range(len(self._m_unordered), 0, -1):
                    for comb_un in itertools.combinations(self._m_unordered, k):
                        with branch(1):  # sic!
                            for un, ord in zip(comb_un, self._m_ordered):
                                connect_methods(m, un, ord)
        return m


class PriorityOrderingProxyTrans(PriorityOrderingTransProxyTrans):
    """Proxy for ordering methods

    Gender changing wrapper for PriorityOrderingTransProxyTrans.

    Attributes
    ----------
    m_unordered : list[Method]
        Calls to these methods will be ordered.
    """

    def __init__(self, methods_ordered: list[Method]):
        """
        Parameters
        ----------
        methods_ordered : list[Method]
            A list of methods which will be called in order. So if `j`-th method
            is called and `i<j` then `i`-th Method also is called.
        """
        self._m_connects = [
            Connect(methods_ordered[0].data_in.layout, methods_ordered[0].data_out.layout) for _ in methods_ordered
        ]
        _m_unordered_read = [connect.read for connect in self._m_connects]
        super().__init__(methods_ordered, _m_unordered_read)
        self.m_unordered = [connect.write for connect in self._m_connects]

    def elaborate(self, platform):
        m = super().elaborate(platform)
        m.submodules.connects = ModuleConnector(*self._m_connects)
        return m


class RegisterPipe(Elaboratable):
    """
    This module allows registers to be written only when
    all ports are ready, but data can be read one by one.
    This is useful if we need to process batches of data
    where order within batch doesn't matter, but the order
    between batches does.

    Attributes
    ----------
    read_list: list[Method]
        The read methods. Accepts an empty argument, returns a `Record`.
    write_list: list[Method]
        The write method. Accepts a `Record`, returns empty result.
    """

    def __init__(self, layout: LayoutLike, channels: int):
        """
        Parameters
        ----------
        layout : LayoutLike
            Layout of the stored data.
        channels : int
            The number of read and write methods to create.
        """
        self.layout = layout
        self.channels = channels

        self.write_list = [Method(i=self.layout) for _ in range(self.channels)]
        self.read_list = [Method(o=self.layout) for _ in range(self.channels)]

    def elaborate(self, platform) -> TModule:
        m = TModule()

        registers = [Register(self.layout) for _ in range(self.channels)]
        m.submodules.registers = ModuleConnector(*registers)

        all_write_ready = Cat(reg.write.ready for reg in registers).all()

        @loop_def_method(m, self.write_list, ready_list=lambda _: all_write_ready)
        def _(i, arg):
            registers[i].write(m, arg)

        @loop_def_method(m, self.read_list)
        def _(i):
            return registers[i].read(m)

        return m


class ShiftRegister(Elaboratable):
    """
    This module implements a shift register. It allows the serialisation of
    a batch of requests. It assumes that the `write` methods are called
    in order (from the method with the lowest index in the list, to
    the method with the biggest index in the list) and next forwards
    received data to the `put` method in order of methods from the list.
    So the data from the 0-th method will be transfered first, next from
    the 1-st method and so on.

    Attributes
    ----------
    write_list : list[Method]
        Methods to write data. Either all or none are ready.
    """

    def __init__(self, layout: LayoutLike, entries_number: int, put: Method, *, first_transparent: bool = True):
        """
        Parameters
        ----------
        layout : LayoutLike
            The layout of the stored data.
        entries_number : int
            The number of entries that can be written at once into
            the shift register.
        put : Method
            The method to call to pass serialised data.
        first_transparent : bool
            Decide whether the call to first write should be transparent
            and passed directly to `put`, or if first should be
            stored into a register.
        """
        self.layout = layout
        self.entries_number = entries_number
        self.put = put
        self.first_transparent = first_transparent

        self.write_list = [Method(i=self.layout) for _ in range(entries_number)]

    def elaborate(self, platform) -> TModule:
        m = TModule()

        regs = [Signal(len(Record(self.layout))) for _ in range(self.entries_number)]
        valids = [Signal() for _ in range(self.entries_number)]
        ready = Signal(reset=1)
        start = Signal()

        reg_now = Signal.like(regs[0])
        reg_now_v = Signal()
        execute_put = Transaction()
        with m.FSM():
            with m.State("start"):
                if self.first_transparent:
                    if self.entries_number > 1:
                        with m.If(start & self.write_list[1].run):
                            m.next = "1"
                else:
                    with m.If(start):
                        m.next = "0"
            for i in range(self.first_transparent, self.entries_number):
                with m.State(f"{i}"):
                    m.d.comb += ready.eq(0)
                    if i + 1 == self.entries_number:
                        with m.If(execute_put.grant):
                            m.next = "start"
                    else:
                        with m.If(valids[i + 1] & execute_put.grant):
                            m.next = f"{i+1}"
                        with m.Elif(execute_put.grant):
                            m.next = "start"
                    m.d.comb += reg_now.eq(regs[i])
                    m.d.comb += reg_now_v.eq(1)
                    m.d.sync += valids[i].eq(0)

        with execute_put.body(m, request=reg_now_v):
            self.put(m, reg_now)

        @loop_def_method(m, self.write_list, lambda _: ready)
        def _(i, arg):
            if i == 0:
                m.d.comb += start.eq(1)
            if self.first_transparent and i == 0:
                self.put(m, arg)
            else:
                m.d.sync += regs[i].eq(arg)
                m.d.sync += valids[i].eq(1)

        return m


class MethodBrancherIn:
    """Syntax sugar for calling the same method in different `m.If` branches.

    Sometimes it is handy to write:

    .. highlight:: python
    .. code-block:: python

        with Transaction().body(m):
            with m.If(cond):
                method(arg1)
            with m.Else():
                method(arg2)

    But such code is not allowed, because a method is called twice in a transaction.
    So normaly it has to be rewritten to:

    .. highlight:: python
    .. code-block:: python

        rec = Record(method.data_in.layout)
        with Transaction().body(m):
            with m.If(cond):
                m.d.comb += assign(rec, arg1)
            with m.Else():
                m.d.comb += assign(rec, arg2)
            method(rec)

    But such a form is less readable. `MethodBrancherIn` is designed to do this
    transformation automatically, so you can write:

    .. highlight:: python
    .. code-block:: python

        with Transaction().body(m):
            b_method = MethodBrancherIn(m, method)
            with m.If(cond):
                b_method(arg1)
            with m.Else():
                b_method(arg2)

    IMPORTANT: `MethodBrancherIn` is constructed within a `Transaction` or
    `Method` that should call the passed `method`. It creates a call in `__init__`.
    """

    def __init__(self, m: TModule, method: Method):
        """
        Parameters
        ----------
        m : TModule
            Module to add connections to.
        method : Method
            Method to wrap.
        """
        self.m = m
        self.method = method
        self.rec_in = Record(method.data_in.layout)
        self.valid_in = Signal()
        with self.m.If(self.valid_in):
            method(m, self.rec_in)

    def __call__(self, args):
        self.m.d.comb += self.rec_in.eq(args)
        self.m.d.comb += self.valid_in.eq(1)


class NotMethod:
    """
    Temporary workaround for bug in where passing a single_caller Method
    as an argument to SimpleTestCircuit connects a second caller.
    """

    def __init__(self, method: Method):
        self.method = method


class DownCounter(Elaboratable):
    def __init__(self, width : int, callback : Method):
        self.width = width
        self.callback = callback

        self.set_start = Method(i=[("start", width)])
        self.tick = Method()


    def elaborate(self, platform):
        m = TModule()

        value = Signal(self.width)
        running = Signal()

        @def_method(m, self.set_start)
        def _ (start):
            m.d.sync += value.eq(start)
            with m.If(start!=0):
                m.d.sync += running.eq(1)

        @def_method(m, self.tick)
        def _():
            cond_signal = Signal()
            with condition(m, nonblocking= False) as branch:
                m.d.top_comb += cond_signal.eq((value == 1) & running)
                with branch(cond_signal):
                    self.callback(m)
                    m.d.sync += running.eq(0)
                with branch(~cond_signal):
                    m.d.sync += value.eq(value-1)

        return m

class Barrier(Elaboratable):
    def __init__(self, layout, port_count : int):
        self.layout = layout
        self.port_count = port_count
        self.layout_out = [(f"out{i}", self.layout) for i in  range(self.port_count)]

        self.write_list = [Method(i = self.layout) for _ in range(self.port_count)]
        self.read = Method(o = self.layout_out)
        self.set_valids = Method(i =[("valids", self.port_count)])

    def elaborate(self, platform):
        m = TModule()

        valids = Signal(self.port_count)
        data = [Record(self.layout) for _ in range(self.port_count)]
        data_current = [Record(self.layout) for _ in range(self.port_count)]
        data_valids = [Signal() for _ in range(self.port_count)]
        
        for write in self.write_list:
            write.schedule_before(self.read)
        @loop_def_method(m, self.write_list, ready_list = lambda i: ~data_valids[i])
        def _(i, arg):
            m.d.sync += data_valids[i].eq(1)
            m.d.sync += data[i].eq(arg)
            m.d.top_comb += data_current[i].eq(arg)

        all_ready = Signal()
        m.d.top_comb += all_ready.eq((~valids | Cat(data_valids) | Cat([w.run for w in self.write_list])).all())
        out_data = Record(self.layout_out)
        @def_method(m, self.read, ready = all_ready)
        def _():
            for i in range(self.port_count):
                m.d.sync += data_valids[i].eq(0)
                m.d.top_comb += out_data[f"out{i}"].eq(Mux(data_valids[i], data[i], Mux(self.write_list[i].run, data_current[i], 0)))
            return out_data

        @def_method(m, self.set_valids)
        def _(arg):
            m.d.sync += valids.eq(arg.valids)

        return m

class ContentAddressableMemory(Elaboratable):
    # This module can be optimised to have O(log n) critical path instead of O(n)
    def __init__(self, address_layout : LayoutLike, data_layout : LayoutLike, entries_number : int):
        self.address_layout = address_layout
        self.data_layout = data_layout
        self.entries_number = entries_number

        self.pop= Method(i=[("addr", self.address_layout)], o=[("data", self.data_layout), ("not_found", 1)])
        self.push = Method(i=[("addr", self.address_layout), ("data", self.data_layout)])


    def elaborate(self, platform) -> TModule:
        m = TModule()

        address_array = Array([Record(self.address_layout) for _ in range(self.entries_number)])
        data_array = Array([Record(self.data_layout) for _ in range(self.entries_number)])
        valids = Signal(self.entries_number, name = "valids")

        m.submodules.encoder_addr = encoder_addr = MultiPriorityEncoder(self.entries_number, 1)
        m.submodules.encoder_valids = encoder_valids = MultiPriorityEncoder(self.entries_number, 1)
        m.d.comb += encoder_valids.input.eq(~valids)

        @def_method(m, self.push, ready=~valids.all())
        def _(addr, data):
            id = Signal(range(self.entries_number), name = "id_push")
            m.d.comb += id.eq(encoder_valids.outputs[0])
            m.d.sync += address_array[id].eq(addr)
            m.d.sync += data_array[id].eq(data)
            m.d.sync += valids.bit_select(id, 1).eq(1)

        if_addr = Signal(self.entries_number, name="if_addr")
        data_to_send = Record(self.data_layout)
        @def_method(m, self.pop)
        def _(addr):
            m.d.top_comb += if_addr.eq(Cat([addr == stored_addr for stored_addr in address_array]) & valids)
            id = encoder_addr.outputs[0]
            with m.If(if_addr.any()):
                m.d.comb += data_to_send.eq(data_array[id])
                m.d.sync += valids.bit_select(id, 1).eq(0)

            return {"data": data_to_send, "not_found": ~if_addr.any()}
        m.d.comb += encoder_addr.input.eq(if_addr)
        
        return m
