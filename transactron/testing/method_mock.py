from contextlib import contextmanager
import functools
from typing import Callable, Any, Optional

from amaranth.sim._async import SimulatorContext
from transactron.lib.adapters import Adapter
from transactron.utils.transactron_helpers import async_mock_def_helper
from .testbenchio import TestbenchIO
from transactron.utils._typing import RecordIntDict


__all__ = ["MethodMock", "def_method_mock"]


class MethodMock:
    def __init__(
        self,
        adapter: Adapter,
        function: Callable[..., Optional[RecordIntDict]],
        *,
        validate_arguments: Optional[Callable[..., bool]] = None,
        enable: Callable[[], bool] = lambda: True,
        delay: float = 0,
    ):
        self.adapter = adapter
        self.function = function
        self.validate_arguments = validate_arguments
        self.enable = enable
        self.delay = delay
        self._effects: list[Callable[[], None]] = []
        self._freeze = False

    _current_mock: Optional["MethodMock"] = None

    @staticmethod
    def effect(effect: Callable[[], None]):
        assert MethodMock._current_mock is not None
        MethodMock._current_mock._effects.append(effect)

    @contextmanager
    def _context(self):
        assert MethodMock._current_mock is None
        MethodMock._current_mock = self
        try:
            yield
        finally:
            MethodMock._current_mock = None

    async def output_process(
        self,
        sim: SimulatorContext,
    ) -> None:
        sync = sim._design.lookup_domain("sync", None)  # type: ignore
        async for *_, done, arg, clk in sim.changed(self.adapter.done, self.adapter.data_out).edge(sync.clk, 1):
            if clk:
                self._freeze = True
            if not done or self._freeze:
                continue
            self._effects = []
            with self._context():
                ret = async_mock_def_helper(self, self.function, arg)
            sim.set(self.adapter.data_in, ret)

    async def validate_arguments_process(self, sim: SimulatorContext) -> None:
        assert self.validate_arguments is not None
        sync = sim._design.lookup_domain("sync", None)  # type: ignore
        async for *args, clk in sim.changed(*(a for a, _ in self.adapter.validators)).edge(sync.clk, 1):
            assert len(args) == len(self.adapter.validators)  # TODO: remove later
            if clk:
                self._freeze = True
            if self._freeze:
                continue
            for arg, r in zip(args, (r for _, r in self.adapter.validators)):
                sim.set(r, async_mock_def_helper(self, self.validate_arguments, arg))

    async def effect_process(self, sim: SimulatorContext) -> None:
        async for *_, done in sim.tick().sample(self.adapter.done):
            # First, perform pending effects, updating internal state.
            with sim.critical():
                if done:
                    for eff in self._effects:
                        eff()

            # Ensure that the effects of all mocks are applied
            await sim.delay(1e-12)
            await sim.delay(self.delay)

            # Next, update combinational signals taking the new state into account.
            # In case the input signals get updated later, the other processes will perform the update again.
            self._effects = []
            self._freeze = False
            if self.validate_arguments is not None:
                for a, r in self.adapter.validators:
                    sim.set(r, async_mock_def_helper(self, self.validate_arguments, sim.get(a)))
            with self._context():
                ret = async_mock_def_helper(self, self.function, sim.get(self.adapter.data_out))
            sim.set(self.adapter.data_in, ret)
            sim.set(self.adapter.en, self.enable())


def def_method_mock(
    tb_getter: Callable[[], TestbenchIO] | Callable[[Any], TestbenchIO], **kwargs
) -> Callable[[Callable[..., Optional[RecordIntDict]]], Callable[[], MethodMock]]:
    """
    Decorator function to create method mock handlers. It should be applied on
    a function which describes functionality which we want to invoke on method call.
    This function will be called on every clock cycle when the method is active,
    and also on combinational changes to inputs.

    The decorated function can have a single argument `arg`, which receives
    the arguments passed to a method as a `data.Const`, or multiple named arguments,
    which correspond to named arguments of the method.

    This decorator can be applied to function definitions or method definitions.
    When applied to a method definition, lambdas passed to `async_def_method_mock`
    need to take a `self` argument, which should be the first.

    Any side effects (state modification, assertions, etc.) need to be guarded
    using the `MethodMock.effect` decorator.

    Make sure to defer accessing state, since decorators are evaluated eagerly
    during function declaration.

    Parameters
    ----------
    tb_getter : Callable[[], TestbenchIO] | Callable[[Any], TestbenchIO]
        Function to get the TestbenchIO of the mocked method.
    enable : Callable[[], bool] | Callable[[Any], bool]
        Function which decides if the method is enabled in a given clock cycle.
    validate_arguments : Callable[..., bool]
        Function which validates call arguments. This applies only to Adapters
        with `with_validate_arguments` set to True.
    delay : float
        Simulation time delay for method mock calling. Used for synchronization
        between different mocks and testbench processes.

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

    def decorator(func: Callable[..., Optional[RecordIntDict]]) -> Callable[[], MethodMock]:
        @functools.wraps(func)
        def mock(func_self=None, /) -> MethodMock:
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
            assert isinstance(tb.adapter, Adapter)
            return MethodMock(tb.adapter, f, **kw)

        mock._transactron_method_mock = 1  # type: ignore
        return mock

    return decorator
