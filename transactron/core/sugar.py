from collections.abc import Sequence, Callable
from amaranth import *
from typing import TYPE_CHECKING, Optional, Concatenate, ParamSpec
from transactron.utils import *
from transactron.utils.assign import AssignArg
from functools import partial

if TYPE_CHECKING:
    from .tmodule import TModule
    from .method import Method

__all__ = ["def_method", "def_methods"]


P = ParamSpec("P")


def def_method(
    m: "TModule",
    method: "Method",
    ready: ValueLike = C(1),
    validate_arguments: Optional[Callable[..., ValueLike]] = None,
):
    """Define a method.

    This decorator allows to define transactional methods in an
    elegant way using Python's `def` syntax. Internally, `def_method`
    uses `Method.body`.

    The decorated function should take keyword arguments corresponding to the
    fields of the method's input layout. The `**kwargs` syntax is supported.
    Alternatively, it can take one argument named `arg`, which will be a
    structure with input signals.

    The returned value can be either a structure with the method's output layout
    or a dictionary of outputs.

    Parameters
    ----------
    m: TModule
        Module in which operations on signals should be executed.
    method: Method
        The method whose body is going to be defined.
    ready: Signal
        Signal to indicate if the method is ready to be run. By
        default it is `Const(1)`, so the method is always ready.
        Assigned combinationally to the `ready` attribute.
    validate_arguments: Optional[Callable[..., ValueLike]]
        Function that takes input arguments used to call the method
        and checks whether the method can be called with those arguments.
        It instantiates a combinational circuit for each
        method caller. By default, there is no function, so all arguments
        are accepted.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        m = Module()
        my_sum_method = Method(i=[("arg1",8),("arg2",8)], o=[("res",8)])
        @def_method(m, my_sum_method)
        def _(arg1, arg2):
            return arg1 + arg2

    Alternative syntax (keyword args in dictionary):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(**args):
            return args["arg1"] + args["arg2"]

    Alternative syntax (arg structure):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(arg):
            return {"res": arg.arg1 + arg.arg2}
    """

    def decorator(func: Callable[..., Optional[AssignArg]]):
        out = Signal(method.layout_out)
        ret_out = None

        with method.body(m, ready=ready, out=out, validate_arguments=validate_arguments) as arg:
            ret_out = method_def_helper(method, func, arg)

        if ret_out is not None:
            m.d.top_comb += assign(out, ret_out, fields=AssignType.ALL)

    return decorator


def def_methods(
    m: "TModule",
    methods: Sequence["Method"],
    ready: Callable[[int], ValueLike] = lambda _: C(1),
    validate_arguments: Optional[Callable[..., ValueLike]] = None,
):
    """Decorator for defining similar methods

    This decorator is a wrapper over `def_method`, which allows you to easily
    define multiple similar methods in a loop.

    The function over which this decorator is applied, should always expect
    at least one argument, as the index of the method will be passed as the
    first argument to the function.

    This is a syntax sugar equivalent to:

    .. highlight:: python
    .. code-block:: python

        for i in range(len(my_methods)):
            @def_method(m, my_methods[i])
            def _(arg):
                ...

    Parameters
    ----------
    m: TModule
        Module in which operations on signals should be executed.
    methods: Sequence[Method]
        The methods whose body is going to be defined.
    ready: Callable[[int], Value]
        A `Callable` that takes the index in the form of an `int` of the currently defined method
        and produces a `Value` describing whether the method is ready to be run.
        When omitted, each defined method is always ready. Assigned combinationally to the `ready` attribute.
    validate_arguments: Optional[Callable[Concatenate[int, ...], ValueLike]]
        Function that takes input arguments used to call the method
        and checks whether the method can be called with those arguments.
        It instantiates a combinational circuit for each
        method caller. By default, there is no function, so all arguments
        are accepted.

    Examples
    --------
    Define three methods with the same body:

    .. highlight:: python
    .. code-block:: python

        m = TModule()
        my_sum_methods = [Method(i=[("arg1",8),("arg2",8)], o=[("res",8)]) for _ in range(3)]
        @def_methods(m, my_sum_methods)
        def _(_, arg1, arg2):
            return arg1 + arg2

    Define three methods with different bodies parametrized with the index of the method:

    .. highlight:: python
    .. code-block:: python

        m = TModule()
        my_sum_methods = [Method(i=[("arg1",8),("arg2",8)], o=[("res",8)]) for _ in range(3)]
        @def_methods(m, my_sum_methods)
        def _(index : int, arg1, arg2):
            return arg1 + arg2 + index

    Define three methods with different ready signals:

    .. highlight:: python
    .. code-block:: python

        @def_methods(m, my_filter_read_methods, ready_list=lambda i: fifo.head == i)
        def _(_):
            return fifo.read(m)
    """

    def decorator(func: Callable[Concatenate[int, P], Optional[RecordDict]]):
        for i in range(len(methods)):
            partial_f = partial(func, i)
            partial_vargs = partial(validate_arguments, i) if validate_arguments is not None else None
            def_method(m, methods[i], ready(i), partial_vargs)(partial_f)

    return decorator
