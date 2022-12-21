import unittest
import os
from contextlib import contextmanager, nullcontext
from typing import Callable, Mapping, Union, Generator, TypeVar, Optional, Any, cast

from amaranth import *
from amaranth.hdl.ast import Statement
from amaranth.sim import *
from amaranth.sim.core import Command
from coreblocks.transactions.core import DebugSignals
from coreblocks.transactions.lib import AdapterBase
from coreblocks.utils._typing import ValueLike, is_two_arg_callable
from .gtkw_extension import write_vcd_ext
from inspect import signature


T = TypeVar("T")
RecordValueDict = Mapping[str, Union[ValueLike, "RecordValueDict"]]
RecordIntDict = Mapping[str, Union[int, "RecordIntDict"]]
RecordIntDictRet = Mapping[str, Any]  # full typing hard to work with
TestGen = Generator[Command | Value | Statement | None, Any, T]


def set_inputs(values: RecordValueDict, field: Record) -> TestGen[None]:
    for name, value in values.items():
        if isinstance(value, dict):
            yield from set_inputs(value, getattr(field, name))
        else:
            yield getattr(field, name).eq(value)


def get_outputs(field: Record) -> TestGen[RecordIntDict]:
    # return dict of all signal values in a record because amaranth's simulator can't read all
    # values of a Record in a single yield - it can only read Values (Signals)
    result = {}
    for name, _, _ in field.layout:
        val = getattr(field, name)
        if isinstance(val, Signal):
            result[name] = yield val
        else:  # field is a Record
            result[name] = yield from get_outputs(val)
    return result


def neg(x: int, xlen: int) -> int:
    """
    Computes the negation of a number in the U2 system.

    Parameters
    ----------
    x: int
        Number in U2 system.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Negation of x in the U2 system.
    """
    return (-x) & (2**xlen - 1)


def int_to_signed(x: int, xlen: int) -> int:
    """
    Converts a Python integer into its U2 representation.

    Parameters
    ----------
    x: int
        Signed Python integer.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Representation of x in the U2 system.
    """
    return x & (2**xlen - 1)


def signed_to_int(x: int, xlen: int) -> int:
    """
    Changes U2 representation into Python integer

    Parameters
    ----------
    x: int
        Number in U2 system.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Representation of x as signed Python integer.
    """
    return x | -(x & (2 ** (xlen - 1)))


class TestCaseWithSimulator(unittest.TestCase):
    @contextmanager
    def runSimulation(self, module, max_cycles=10e4, extra_signals=()):
        test_name = unittest.TestCase.id(self)
        clk_period = 1e-6

        sim = Simulator(module)
        sim.add_clock(clk_period)
        yield sim

        if "__COREBLOCKS_DUMP_TRACES" in os.environ:
            traces_dir = "test/__traces__"
            os.makedirs(traces_dir, exist_ok=True)

            # Signal handling is hacky and accesses Simulator internals.
            # TODO: try to merge with Amaranth.
            if isinstance(extra_signals, Callable):
                extra_signals = extra_signals()
            clocks = [d.clk for d in cast(Any, sim)._fragment.domains.values()]

            ctx = write_vcd_ext(
                cast(Any, sim)._engine,
                f"{traces_dir}/{test_name}.vcd",
                f"{traces_dir}/{test_name}.gtkw",
                traces=[clocks, extra_signals],
            )
        else:
            ctx = nullcontext()

        with ctx:
            sim.run_until(clk_period * max_cycles)
            self.assertFalse(sim.advance(), "Simulation time limit exceeded")


class TestbenchIO(Elaboratable):
    def __init__(self, adapter: AdapterBase):
        self.adapter = adapter

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    # Low-level operations

    def enable(self) -> TestGen[None]:
        yield self.adapter.en.eq(1)

    def disable(self) -> TestGen[None]:
        yield self.adapter.en.eq(0)

    def done(self) -> TestGen[int]:
        return (yield self.adapter.done)

    def wait_until_done(self) -> TestGen[None]:
        while (yield self.adapter.done) != 1:
            yield

    def set_inputs(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from set_inputs(data, self.adapter.data_in)

    def get_outputs(self) -> TestGen[RecordIntDictRet]:
        return (yield from get_outputs(self.adapter.data_out))

    # Operations for AdapterTrans

    def call_init(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from self.enable()
        yield from self.set_inputs(data)

    def call_result(self) -> TestGen[Optional[RecordIntDictRet]]:
        if (yield from self.done()):
            return (yield from self.get_outputs())
        return None

    def call_do(self) -> TestGen[RecordIntDict]:
        while (outputs := (yield from self.call_result())) is None:
            yield
        yield from self.disable()
        return outputs

    def call_try(self, data: RecordIntDict = {}) -> TestGen[Optional[RecordIntDictRet]]:
        yield from self.call_init(data)
        yield
        outputs = yield from self.call_result()
        yield from self.disable()
        return outputs

    def call(self, data: RecordIntDict = {}) -> TestGen[RecordIntDictRet]:
        yield from self.call_init(data)
        yield
        return (yield from self.call_do())

    # Operations for Adapter

    def method_argument(self) -> TestGen[Optional[RecordIntDictRet]]:
        return (yield from self.call_result())

    def method_return(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from self.set_inputs(data)

    def method_handle(
        self, function: Callable[[RecordIntDictRet], Optional[RecordIntDict]], *, settle: int = 0
    ) -> TestGen[None]:
        for _ in range(settle):
            yield Settle()
        while (arg := (yield from self.method_argument())) is None:
            yield
            for _ in range(settle):
                yield Settle()
        yield from self.method_return(function(arg) or {})
        yield

    def method_handle_loop(
        self,
        function: Callable[[RecordIntDictRet], Optional[RecordIntDict]],
        *,
        settle: int = 0,
        enable: bool = True,
        condition: Optional[Callable[[], bool]] = None,
    ) -> TestGen[None]:
        if condition is None:
            yield Passive()
        condition = condition or (lambda: True)
        if enable:
            yield from self.enable()
        while condition():
            yield from self.method_handle(function, settle=settle)

    # Debug signals

    def debug_signals(self) -> DebugSignals:
        return self.adapter.debug_signals()


def _getattr_deep(obj, path: str):
    value = obj
    for field in path.split("."):
        if "[" in field:
            assert "]" in field
            listName, _, rest = field.partition("[")
            idx, _, _ = rest.partition("]")
            value = getattr(value, listName)
            value = value[int(idx)]
        else:
            value = getattr(value, field)
    return value


def def_method_mock(name: str, circut: Optional[Elaboratable] = None, **kwargs):
    """
    Decorator function to create method mock handlers. It should be applied on
    a function which describe functionality which we wan't to invoke on method call.
    Such function will be wrapped by `method_handle_loop` and called on each
    method invocation.

    If `def_method_mock` wrapps a function `f` then it is expected that:
    - `f` has exactly one argument when `circuit` is not `None` and this
        argument are data passed as an input to method
    - `f` has exactly two arguments when `circuit` is `None` in such
        case first is expected to be `self` and second are data passed
        as an input to method

    Function wrapped by `def_method_mock` should return data which will be sent
    as response to method call.

    Please remember that decorators are fully evaluated when function is defined.

    Parameters
    ----------
    name : str
        Name of the `TestbenchIO` field in class. If `circut` is not none, then
        `name` decribe field in `circut` else it is expected that wrapped function
        take `self` argument and `name` is a field of `self`. Name can be multilayer
        path and can index lists with int's known on function definition time.
    circut : Elaboratable
        Eleboratable which have as a field (or as a nested field) a TestbenchIO instance
        to which we should connect with our mock.
    **kwargs
        Arguments passed to `method_handle_loop`.

    Example
    -------
    In this example `self.m.target` is an instance of TestbenchIO which we want to
    wrap. We get some data `v` and as a result we return `v` incremented by 1.
    `settle=1` is an argument passed to `method_handle_loop`.
    ```
    @def_method_mock("m.target", settle=1)
    def target(self, v):
        return {"data": v["data"] + 1}
    ```

    On the other hand here we have a test circuit which we know on definition time
    and isn't dependend from `self` so we pass it as `circuit` argument. In such case
    wrapped process take only input data. This example also present a generator of
    method handlers. By invoking `target_process` with different `k` we create
    new instances of handlers. Each handler is connected to different TestbenchIO, by
    indexing list of targets TestbenchIO's. Please note that `k` is known in time
    of definition of process and is passed in numerical form to `name` string.
    ```
    m = TestCircuit()
    def target_process(k: int):
        @def_method_mock(f"target[{k}]", m, settle=1, enable=False)
        def process(v):
            return {"data": v["data"] + k}
        return process
    ```
    """

    def decorator(
        func: Union[
            Callable[[RecordIntDictRet], Optional[RecordIntDict]],
            Callable[[Any, RecordIntDictRet], Optional[RecordIntDict]],
        ]
    ):
        sig = signature(func)
        if circut is None:
            assert len(sig.parameters) == 2
        else:
            assert len(sig.parameters) == 1

        def mock(self: Optional[Any] = None) -> TestGen[None]:
            def partial_appl(x):
                assert is_two_arg_callable(func)
                return func(self, x)

            if circut is None:
                tb = _getattr_deep(self, name)
                f = partial_appl
            else:
                tb = _getattr_deep(circut, name)
                f = func
            assert isinstance(tb, TestbenchIO)
            yield from tb.method_handle_loop(f, **kwargs)

        return mock

    return decorator
