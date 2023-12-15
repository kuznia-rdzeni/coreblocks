import functools
from typing import Callable, Any, Optional
from .testbenchio import TestbenchIO, TestGen
from transactron.utils._typing import RecordIntDict


def def_method_mock(
    tb_getter: Callable[[], TestbenchIO] | Callable[[Any], TestbenchIO], sched_prio: int = 0, **kwargs
) -> Callable[[Callable[..., Optional[RecordIntDict]]], Callable[[], TestGen[None]]]:
    """
    Decorator function to create method mock handlers. It should be applied on
    a function which describes functionality which we want to invoke on method call.
    Such function will be wrapped by `method_handle_loop` and called on each
    method invocation.

    Function `f` should take only one argument `arg` - data used in function
    invocation - and should return data to be sent as response to the method call.

    Function `f` can also be a method and take two arguments `self` and `arg`,
    the data to be passed on to invoke a method.  It should return data to be sent
    as response to the method call.

    Instead of the `arg` argument, the data can be split into keyword arguments.

    Make sure to defer accessing state, since decorators are evaluated eagerly
    during function declaration.

    Parameters
    ----------
    tb_getter : Callable[[], TestbenchIO] | Callable[[Any], TestbenchIO]
        Function to get the TestbenchIO providing appropriate `method_handle_loop`.
    **kwargs
        Arguments passed to `method_handle_loop`.

    Example
    -------
    ```
    m = TestCircuit()
    def target_process(k: int):
        @def_method_mock(lambda: m.target[k])
        def process(arg):
            return {"data": arg["data"] + k}
        return process
    ```
    or equivalently
    ```
    m = TestCircuit()
    def target_process(k: int):
        @def_method_mock(lambda: m.target[k], settle=1, enable=False)
        def process(data):
            return {"data": data + k}
        return process
    ```
    or for class methods
    ```
    @def_method_mock(lambda self: self.target[k], settle=1, enable=False)
    def process(self, data):
        return {"data": data + k}
    ```
    """

    def decorator(func: Callable[..., Optional[RecordIntDict]]) -> Callable[[], TestGen[None]]:
        @functools.wraps(func)
        def mock(func_self=None, /) -> TestGen[None]:
            f = func
            getter: Any = tb_getter
            kw = kwargs
            if func_self is not None:
                getter = getter.__get__(func_self)
                f = f.__get__(func_self)
                kw = {}
                for k, v in kwargs.items():
                    bind = getattr(v, "__get__", None)
                    kw[k] = bind(func_self) if bind else v
            tb = getter()
            assert isinstance(tb, TestbenchIO)
            yield from tb.method_handle_loop(f, extra_settle_count=sched_prio, **kw)

        mock._transactron_testing_process = 1  # type: ignore
        return mock

    return decorator
