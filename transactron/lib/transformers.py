from abc import ABC
from amaranth import *

from transactron.utils.transactron_helpers import get_src_loc
from ..core import *
from ..core import RecordDict
from ..utils import SrcLoc
from typing import Optional
from collections.abc import Callable
from transactron.utils import ValueLike, assign, AssignType, ModuleLike
from .connectors import Forwarder, ManyToOneConnectTrans, ConnectTrans
from .simultaneous import condition

__all__ = [
    "Transformer",
    "MethodMap",
    "MethodFilter",
    "MethodProduct",
    "MethodTryProduct",
    "Collector",
    "CatTrans",
    "ConnectAndMapTrans",
]


class Transformer(ABC, Elaboratable):
    """Method transformer abstract class.

    Method transformers construct a new method which utilizes other methods.

    Attributes
    ----------
    method: Method
        The method.
    """

    method: Method

    def use(self, m: ModuleLike):
        """
        Returns the method and adds the transformer to a module.

        Parameters
        ----------
        m: Module or TModule
            The module to which this transformer is added as a submodule.
        """
        m.submodules += self
        return self.method


class MethodMap(Transformer):
    """Bidirectional map for methods.

    Takes a target method and creates a transformed method which calls the
    original target method, mapping the input and output values with
    functions. The mapping functions take two parameters, a `Module` and the
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
        i_transform: Optional[tuple[MethodLayout, Callable[[TModule, Record], RecordDict]]] = None,
        o_transform: Optional[tuple[MethodLayout, Callable[[TModule, Record], RecordDict]]] = None,
        src_loc: int | SrcLoc = 0
    ):
        """
        Parameters
        ----------
        target: Method
            The target method.
        i_transform: (record layout, function or Method), optional
            Input mapping function. If specified, it should be a pair of a
            function and a input layout for the transformed method.
            If not present, input is passed unmodified.
        o_transform: (record layout, function or Method), optional
            Output mapping function. If specified, it should be a pair of a
            function and a output layout for the transformed method.
            If not present, output is passed unmodified.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        if i_transform is None:
            i_transform = (target.data_in.layout, lambda _, x: x)
        if o_transform is None:
            o_transform = (target.data_out.layout, lambda _, x: x)

        self.target = target
        src_loc = get_src_loc(src_loc)
        self.method = Method(i=i_transform[0], o=o_transform[0], src_loc=src_loc)
        self.i_fun = i_transform[1]
        self.o_fun = o_transform[1]

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.method)
        def _(arg):
            return self.o_fun(m, self.target(m, self.i_fun(m, arg)))

        return m


class MethodFilter(Transformer):
    """Method filter.

    Takes a target method and creates a method which calls the target method
    only when some condition is true. The condition function takes two
    parameters, a module and the input `Record` of the method. Non-zero
    return value is interpreted as true. Alternatively to using a function,
    a `Method` can be passed as a condition.
    By default, the target method is locked for use even if it is not called.
    If this is not the desired effect, set `use_condition` to True, but this will
    cause that the provided method will be `single_caller` and all other `condition`
    drawbacks will be in place (e.g. risk of exponential complexity).

    Attributes
    ----------
    method: Method
        The transformed method.
    """

    def __init__(
        self,
        target: Method,
        condition: Callable[[TModule, Record], ValueLike],
        default: Optional[RecordDict] = None,
        *,
        use_condition: bool = False,
        src_loc: int | SrcLoc = 0
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
        use_condition : bool
            Instead of `m.If` use simultaneus `condition` which allow to execute
            this filter if the condition is False and target is not ready.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        if default is None:
            default = Record.like(target.data_out)

        self.target = target
        self.use_condition = use_condition
        src_loc = get_src_loc(src_loc)
        self.method = Method(
            i=target.data_in.layout, o=target.data_out.layout, single_caller=self.use_condition, src_loc=src_loc
        )
        self.condition = condition
        self.default = default

    def elaborate(self, platform):
        m = TModule()

        ret = Record.like(self.target.data_out)
        m.d.comb += assign(ret, self.default, fields=AssignType.ALL)

        @def_method(m, self.method)
        def _(arg):
            if self.use_condition:
                cond = Signal()
                m.d.top_comb += cond.eq(self.condition(m, arg))
                with condition(m, nonblocking=False, priority=False) as branch:
                    with branch(cond):
                        m.d.comb += ret.eq(self.target(m, arg))
                    with branch(~cond):
                        pass
            else:
                with m.If(self.condition(m, arg)):
                    m.d.comb += ret.eq(self.target(m, arg))
            return ret

        return m


class MethodProduct(Transformer):
    def __init__(
        self,
        targets: list[Method],
        combiner: Optional[tuple[MethodLayout, Callable[[TModule, list[Record]], RecordDict]]] = None,
        *,
        src_loc: int | SrcLoc = 0
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
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.

        Attributes
        ----------
        method: Method
            The product method.
        """
        if combiner is None:
            combiner = (targets[0].data_out.layout, lambda _, x: x[0])
        self.targets = targets
        self.combiner = combiner
        src_loc = get_src_loc(src_loc)
        self.method = Method(i=targets[0].data_in.layout, o=combiner[0], src_loc=src_loc)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.method)
        def _(arg):
            results = []
            for target in self.targets:
                results.append(target(m, arg))
            return self.combiner[1](m, results)

        return m


class MethodTryProduct(Transformer):
    def __init__(
        self,
        targets: list[Method],
        combiner: Optional[tuple[MethodLayout, Callable[[TModule, list[tuple[Value, Record]]], RecordDict]]] = None,
        *,
        src_loc: int | SrcLoc = 0
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
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.

        Attributes
        ----------
        method: Method
            The product method.
        """
        if combiner is None:
            combiner = ([], lambda _, __: {})
        self.targets = targets
        self.combiner = combiner
        self.src_loc = get_src_loc(src_loc)
        self.method = Method(i=targets[0].data_in.layout, o=combiner[0], src_loc=self.src_loc)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.method)
        def _(arg):
            results: list[tuple[Value, Record]] = []
            for target in self.targets:
                success = Signal()
                with Transaction(src_loc=self.src_loc).body(m):
                    m.d.comb += success.eq(1)
                    results.append((success, target(m, arg)))
            return self.combiner[1](m, results)

        return m


class Collector(Transformer):
    """Single result collector.

    Creates method that collects results of many methods with identical
    layouts. Each call of this method will return a single result of one
    of the provided methods.

    Attributes
    ----------
    method: Method
        Method which returns single result of provided methods.
    """

    def __init__(self, targets: list[Method], *, src_loc: int | SrcLoc = 0):
        """
        Parameters
        ----------
        method_list: list[Method]
            List of methods from which results will be collected.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.method_list = targets
        layout = targets[0].data_out.layout
        self.src_loc = get_src_loc(src_loc)
        self.method = Method(o=layout, src_loc=self.src_loc)

        for method in targets:
            if layout != method.data_out.layout:
                raise Exception("Not all methods have this same layout")

    def elaborate(self, platform):
        m = TModule()

        m.submodules.forwarder = forwarder = Forwarder(self.method.data_out.layout, src_loc=self.src_loc)

        m.submodules.connect = ManyToOneConnectTrans(
            get_results=[get for get in self.method_list], put_result=forwarder.write, src_loc=self.src_loc
        )

        self.method.proxy(m, forwarder.read)

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


class ConnectAndMapTrans(Elaboratable):
    """Connecting transaction with mapping functions.

    Behaves like `ConnectTrans`, but modifies the transferred data using
    functions or `Method`s. Equivalent to a combination of `ConnectTrans`
    and `MethodMap`. The mapping functions take two parameters, a `Module`
    and the `Record` being transformed.
    """

    def __init__(
        self,
        method1: Method,
        method2: Method,
        *,
        i_fun: Optional[Callable[[TModule, Record], RecordDict]] = None,
        o_fun: Optional[Callable[[TModule, Record], RecordDict]] = None,
        src_loc: int | SrcLoc = 0
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
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        self.method1 = method1
        self.method2 = method2
        self.i_fun = i_fun or (lambda _, x: x)
        self.o_fun = o_fun or (lambda _, x: x)
        self.src_loc = get_src_loc(src_loc)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.transformer = transformer = MethodMap(
            self.method2,
            i_transform=(self.method1.data_out.layout, self.i_fun),
            o_transform=(self.method1.data_in.layout, self.o_fun),
            src_loc=self.src_loc,
        )
        m.submodules.connect = ConnectTrans(self.method1, transformer.method)

        return m
