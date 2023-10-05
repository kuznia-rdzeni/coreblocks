from amaranth import *
from ..core import *
from ..core import RecordDict
from typing import Optional, Callable
from . import methods

__all__ = [
    "ConnectTrans",
    "ConnectAndTransformTrans",
    "CatTrans",
    "ManyToOneConnectTrans",
]


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
            data1 = Record.like(self.method1.data_out)
            data2 = Record.like(self.method2.data_out)

            m.d.top_comb += data1.eq(self.method1(m, data2))
            m.d.top_comb += data2.eq(self.method2(m, data1))

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

        m.submodules.transformer = transformer = methods.MethodTransformer(
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

            m.d.comb += ddata.eq(Cat(sdata1, sdata2))

        return m
