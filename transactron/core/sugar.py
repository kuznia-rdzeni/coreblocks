from amaranth import *
from typing import TYPE_CHECKING, Optional, Callable
from transactron.utils import *
from transactron.utils.assign import AssignArg

if TYPE_CHECKING:
    from .tmodule import TModule
    from .method import Method

__all__ = ["def_method"]


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
