from typing import Callable, Tuple, Optional
from amaranth import *
from .core import *
from .core import DebugSignals, RecordDict
from ._utils import _coerce_layout, MethodLayout

__all__ = [
    "FIFO",
    "ClickIn",
    "ClickOut",
    "AdapterTrans",
    "Adapter",
    "ConnectTrans",
    "ConnectAndTransformTrans",
    "CatTrans",
    "ManyToOneConnectTrans",
    "MethodFilter",
    "MethodProduct",
]

# FIFOs

import amaranth.lib.fifo


class FIFO(Elaboratable):
    """FIFO module.

    Provides a transactional interface to Amaranth FIFOs. Exposes two methods:
    ``read``, and ``write``. Both methods are ready only when they can
    be executed -- i.e. the queue is respectively not empty / not full.
    It is possible to simultaneously read and write in a single clock cycle,
    but only if both readiness conditions are fulfilled.

    Parameters
    ----------
    layout: int or record layout
        The format of records stored in the FIFO.
    depth: int
        Size of the FIFO.
    fifoType: Elaboratable
        FIFO module conforming to Amaranth library FIFO interface. Defaults
        to SyncFIFO.

    Attributes
    ----------
    read: Method
        The read method. Accepts an empty argument, returns a ``Record``.
    write: Method
        The write method. Accepts a ``Record``, returns empty result.
    """

    def __init__(self, layout: MethodLayout, depth: int, fifoType=amaranth.lib.fifo.SyncFIFO):
        layout = _coerce_layout(layout)
        self.width = len(Record(layout))
        self.depth = depth
        self.fifoType = fifoType

        self.read = Method(o=layout)
        self.write = Method(i=layout)

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = self.fifoType(width=self.width, depth=self.depth)

        assert fifo.fwft  # the read method requires FWFT behavior

        @def_method(m, self.write, ready=fifo.w_rdy)
        def _(arg):
            m.d.comb += fifo.w_en.eq(1)
            m.d.comb += fifo.w_data.eq(arg)

        @def_method(m, self.read, ready=fifo.r_rdy)
        def _(arg):
            m.d.comb += fifo.r_en.eq(1)
            return fifo.r_data

        return m


# "Clicked" input


class ClickIn(Elaboratable):
    """Clicked input.

    Useful for interactive simulations or FPGA button/switch interfaces.
    On a rising edge (tested synchronously) of ``btn``, the ``get`` method
    is enabled, which returns the data present on ``dat`` at the time.
    Inputs are synchronized.

    Parameters
    ----------
    layout: int or record layout
        The data format for the input.

    Attributes
    ----------
    get: Method
        The method for retrieving data from the input. Accepts an empty
        argument, returns a ``Record``.
    btn: Signal, in
        The button input.
    dat: Record, in
        The data input.
    """

    def __init__(self, layout: MethodLayout = 1):
        self.get = Method(o=layout)
        self.btn = Signal()
        self.dat = Record(_coerce_layout(layout))

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
        def _(arg):
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
    On a rising edge (tested synchronously) of ``btn``, the ``put`` method
    is enabled, which, when called, changes the value of the ``dat`` signal.

    Parameters
    ----------
    layout: int or record layout
        The data format for the output.

    Attributes
    ----------
    put: Method
        The method for retrieving data from the input. Accepts a ``Record``,
        returns empty result.
    btn: Signal, in
        The button input.
    dat: Record, out
        The data output.
    """

    def __init__(self, layout: MethodLayout = 1):
        self.put = Method(i=layout)
        self.btn = Signal()
        self.dat = Record(_coerce_layout(layout))

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
    def __init__(self, iface: Method):
        self.iface = iface
        self.en = Signal()
        self.done = Signal()

    def debug_signals(self) -> DebugSignals:
        return [self.en, self.done, self.data_in, self.data_out]


class AdapterTrans(AdapterBase):
    """Adapter transaction.

    Creates a transaction controlled by plain Amaranth signals. Allows to
    expose a method to plain Amaranth code, including testbenches.

    Parameters
    ----------
    iface: Method
        The method to be called by the transaction.

    Attributes
    ----------
    en: Signal, in
        Activates the transaction (sets the ``request`` signal).
    done: Signal, out
        Signals that the transaction is performed (returns the ``grant``
        signal).
    data_in: Record, in
        Data passed to the ``iface`` method.
    data_out: Record, out
        Data returned from the ``iface`` method.
    """

    def __init__(self, iface: Method):
        super().__init__(iface)
        self.data_in = Record.like(iface.data_in)
        self.data_out = Record.like(iface.data_out)

    def elaborate(self, platform):
        m = Module()

        # this forces data_in signal to appear in VCD dumps
        data_in = Signal.like(self.data_in)
        m.d.comb += data_in.eq(self.data_in)

        with Transaction().body(m, request=self.en):
            data_out = self.iface(m, arg=data_in)
            m.d.comb += self.data_out.eq(data_out)
            m.d.comb += self.done.eq(1)

        return m


class Adapter(AdapterBase):
    """Adapter method.

    Creates a method controlled by plain Amaranth signals. One of the
    possible uses is to mock a method in a testbench.

    Parameters
    ----------
    i: int or record layout
        The input layout of the defined method.
    o: int or record layout
        The output layout of the defined method.

    Attributes
    ----------
    en: Signal, in
        Activates the method (sets the ``ready`` signal).
    done: Signal, out
        Signals that the method is called (returns the ``run`` signal).
    data_in: Record, in
        Data returned from the defined method.
    data_out: Record, out
        Data passed as argument to the defined method.
    """

    def __init__(self, *, i: MethodLayout = 0, o: MethodLayout = 0):
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
            m.d.comb += self.data_out.eq(arg)
            m.d.comb += self.done.eq(1)
            return data_in

        return m


# Method combinators


class MethodTransformer(Elaboratable):
    """Method transformer.

    Takes a target method and creates a transformed method which calls the
    original target method, transforming the input and output values.
    The transformation functions take two parameters, a ``Module`` and the
    ``Record`` being transformed. Alternatively, a ``Method`` can be
    passed.

    Parameters
    ----------
    target: Method
        The target method.
    i_transform: (int or record layout, function or Method), optional
        Input transformation. If specified, it should be a pair of a
        function and a input layout for the transformed method.
        If not present, input is not transformed.
    o_transform: (int or record layout, function or Method), optional
        Output transformation. If specified, it should be a pair of a
        function and a output layout for the transformed method.
        If not present, output is not transformed.

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
    parameters, a module and the input ``Record`` of the method. Non-zero
    return value is interpreted as true. Alternatively to using a function,
    a ``Method`` can be passed as a condition.

    Caveat: because of the limitations of transaction scheduling, the target
    method is locked for usage even if it is not called.

    Parameters
    ----------
    target: Method
        The target method.
    condition: function or Method
        The condition which, when true, allows the call to ``target``. When
        false, ``default`` is returned.
    default: Value or dict, optional
        The default value returned from the filtered method when the condition
        is false. If omitted, zero is returned.

    Attributes
    ----------
    method: Method
        The transformed method.
    """

    def __init__(
        self, target: Method, condition: Callable[[Module, Record], RecordDict], default: Optional[RecordDict] = None
    ):
        if default is None:
            default = Record.like(target.data_out)

        self.target = target
        self.method = Method.like(target)
        self.condition = condition
        self.default = default

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.method)
        def _(arg):
            ret = Record.like(self.target.data_out)
            m.d.comb += ret.eq(self.default)
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
            combiner function takes two parameters: a ``Module`` and
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


# Example transactions


class ConnectTrans(Elaboratable):
    """Simple connecting transaction.

    Takes two methods and creates a transaction which calls both of them.
    Result of the first method is connected to the argument of the second,
    and vice versa. Allows easily connecting methods with compatible
    layouts.

    Parameters
    ----------
    method1: Method
        First method.
    method2: Method
        Second method.
    """

    def __init__(self, method1: Method, method2: Method):
        self.method1 = method1
        self.method2 = method2

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            data1 = Record.like(self.method1.data_out)
            data2 = Record.like(self.method2.data_out)

            m.d.comb += data1.eq(self.method1(m, data2))
            m.d.comb += data2.eq(self.method2(m, data1))

        return m


class ConnectAndTransformTrans(Elaboratable):
    """Connecting transaction with transformations.

    Behaves like ``ConnectTrans``, but modifies the transferred data using
    functions or ``Method``s. Equivalent to a combination of
    ``ConnectTrans`` and ``MethodTransformer``. The transformation
    functions take two parameters, a ``Module`` and the ``Record`` being
    transformed.

    Parameters
    ----------
    method1: Method
        First method.
    method2: Method
        Second method, and the method being transformed.
    i_fun: function or Method, optional
        Input transformation (``method1`` to ``method2``).
    o_fun: function or Method, optional
        Output transformation (``method2`` to ``method1``).
    """

    def __init__(
        self,
        method1: Method,
        method2: Method,
        *,
        i_fun: Optional[Callable[[Module, Record], RecordDict]] = None,
        o_fun: Optional[Callable[[Module, Record], RecordDict]] = None,
    ):
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

    Parameters
    ----------
    get_results: list[Method]
        Methods to be connected to the `put_result` method.
    put_result: Method
        Common method for each of the connections created.
    """

    def __init__(self, *, get_results: list[Method], put_result: Method):
        self.get_results = get_results
        self.m_put_result = put_result

        self.count = len(self.get_results)

    def elaborate(self, platfrom):
        m = Module()

        for i in range(self.count):
            setattr(
                m.submodules, f"ManyToOneConnectTrans_input_{i}", ConnectTrans(self.m_put_result, self.get_results[i])
            )

        return m


class CatTrans(Elaboratable):
    """Concatenating transaction.

    Concatenates the results of two methods and passes the result to the
    third method.

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

    def __init__(self, src1: Method, src2: Method, dst: Method):
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
