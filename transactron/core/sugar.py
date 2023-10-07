from amaranth import *
from typing import Callable, Optional
from .modules import TModule
from .method import Method
from .typing import ValueLike, RecordDict
from .._utils import method_def_helper
from coreblocks.utils import assign, AssignType
__all__ = [
    "def_method",
]

def def_method(m: TModule, method: Method, ready: ValueLike = C(1)):
    """Define a method.

    This decorator allows to define transactional methods in an
    elegant way using Python's `def` syntax. Internally, `def_method`
    uses `Method.body`.

    The decorated function should take keyword arguments corresponding to the
    fields of the method's input layout. The `**kwargs` syntax is supported.
    Alternatively, it can take one argument named `arg`, which will be a
    record with input signals.

    The returned value can be either a record with the method's output layout
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

    Alternative syntax (arg record):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(arg):
            return {"res": arg.arg1 + arg.arg2}
    """

    def decorator(func: Callable[..., Optional[RecordDict]]):
        out = Record.like(method.data_out)
        ret_out = None

        with method.body(m, ready=ready, out=out) as arg:
            ret_out = method_def_helper(method, func, arg, **arg.fields)

        if ret_out is not None:
            m.d.top_comb += assign(out, ret_out, fields=AssignType.ALL)

    return decorator
