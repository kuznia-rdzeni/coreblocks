import unittest
import os
import functools
import inspect
from contextlib import contextmanager, nullcontext
from typing import Callable, Generic, Mapping, Union, Generator, TypeVar, Optional, Any, cast, Type, TypeGuard

from amaranth import *
from amaranth.hdl.ast import Statement
from amaranth.sim import *
from amaranth.sim.core import Command

from coreblocks.transactions.core import SignalBundle, Method, TransactionModule
from coreblocks.transactions.lib import AdapterBase, AdapterTrans
from coreblocks.transactions._utils import method_def_helper
from coreblocks.utils import ValueLike, HasElaborate, HasDebugSignals, auto_debug_signals, LayoutLike, ModuleConnector
from .gtkw_extension import write_vcd_ext


T = TypeVar("T")
RecordValueDict = Mapping[str, Union[ValueLike, "RecordValueDict"]]
RecordIntDict = Mapping[str, Union[int, "RecordIntDict"]]
RecordIntDictRet = Mapping[str, Any]  # full typing hard to work with
TestGen = Generator[Command | Value | Statement | None, Any, T]
_T_nested_collection = T | list["_T_nested_collection[T]"] | dict[str, "_T_nested_collection[T]"]


def data_layout(val: int) -> LayoutLike:
    return [("data", val)]


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


def guard_nested_collection(cont: Any, t: Type[T]) -> TypeGuard[_T_nested_collection[T]]:
    if isinstance(cont, (list, dict)):
        if isinstance(cont, dict):
            cont = cont.values()
        return all([guard_nested_collection(elem, t) for elem in cont])
    elif isinstance(cont, t):
        return True
    else:
        return False


_T_HasElaborate = TypeVar("_T_HasElaborate", bound=HasElaborate)


class SimpleTestCircuit(Elaboratable, Generic[_T_HasElaborate]):
    def __init__(self, dut: _T_HasElaborate):
        self._dut = dut
        self._io: dict[str, _T_nested_collection[TestbenchIO]] = {}

    def __getattr__(self, name: str) -> Any:
        return self._io[name]

    def elaborate(self, platform):
        def transform_methods_to_testbenchios(
            container: _T_nested_collection[Method],
        ) -> tuple[_T_nested_collection["TestbenchIO"], Union[ModuleConnector, "TestbenchIO"]]:
            if isinstance(container, list):
                tb_list = []
                mc_list = []
                for elem in container:
                    tb, mc = transform_methods_to_testbenchios(elem)
                    tb_list.append(tb)
                    mc_list.append(mc)
                return tb_list, ModuleConnector(*mc_list)
            elif isinstance(container, dict):
                tb_dict = {}
                mc_dict = {}
                for name, elem in container.items():
                    tb, mc = transform_methods_to_testbenchios(elem)
                    tb_dict[name] = tb
                    mc_dict[name] = mc
                return tb_dict, ModuleConnector(*mc_dict)
            else:
                tb = TestbenchIO(AdapterTrans(container))
                return tb, tb

        m = Module()

        m.submodules.dut = self._dut

        for name, attr in [(name, getattr(self._dut, name)) for name in dir(self._dut)]:
            if guard_nested_collection(attr, Method) and attr:
                tb_cont, mc = transform_methods_to_testbenchios(attr)
                self._io[name] = tb_cont
                m.submodules[name] = mc

        return m

    def debug_signals(self):
        return [auto_debug_signals(io) for io in self._io.values()]


class TestModule(Elaboratable):
    def __init__(self, tested_module: HasElaborate, add_transaction_module):
        self.tested_module = TransactionModule(tested_module) if add_transaction_module else tested_module
        self.add_transaction_module = add_transaction_module

    def elaborate(self, platform) -> HasElaborate:
        m = Module()

        # so that Amaranth allows us to use add_clock
        _dummy = Signal()
        m.d.sync += _dummy.eq(1)

        m.submodules.tested_module = self.tested_module

        return m


class PysimSimulator(Simulator):
    def __init__(self, module: HasElaborate, max_cycles: float = 10e4, add_transaction_module=True, traces_file=None):
        super().__init__(TestModule(module, add_transaction_module))

        clk_period = 1e-6
        self.add_clock(clk_period)

        if isinstance(module, HasDebugSignals):
            extra_signals = module.debug_signals
        else:
            extra_signals = functools.partial(auto_debug_signals, module)

        if traces_file:
            traces_dir = "test/__traces__"
            os.makedirs(traces_dir, exist_ok=True)
            # Signal handling is hacky and accesses Simulator internals.
            # TODO: try to merge with Amaranth.
            if isinstance(extra_signals, Callable):
                extra_signals = extra_signals()
            clocks = [d.clk for d in cast(Any, self)._fragment.domains.values()]

            self.ctx = write_vcd_ext(
                cast(Any, self)._engine,
                f"{traces_dir}/{traces_file}.vcd",
                f"{traces_dir}/{traces_file}.gtkw",
                traces=[clocks, extra_signals],
            )
        else:
            self.ctx = nullcontext()

        self.deadline = clk_period * max_cycles

    def run(self) -> bool:
        with self.ctx:
            self.run_until(self.deadline)

        return not self.advance()


class TestCaseWithSimulator(unittest.TestCase):
    @contextmanager
    def run_simulation(self, module: HasElaborate, max_cycles: float = 10e4, add_transaction_module=True):
        traces_file = None
        if "__COREBLOCKS_DUMP_TRACES" in os.environ:
            traces_file = unittest.TestCase.id(self)

        sim = PysimSimulator(
            module, max_cycles=max_cycles, add_transaction_module=add_transaction_module, traces_file=traces_file
        )
        yield sim
        res = sim.run()

        self.assertTrue(res, "Simulation time limit exceeded")

    def tick(self, cycle_cnt=1):
        """
        Yields for the given number of cycles.
        """

        for _ in range(cycle_cnt):
            yield


class TestbenchIO(Elaboratable):
    def __init__(self, adapter: AdapterBase):
        self.adapter = adapter

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.adapter
        return m

    # Low-level operations

    def set_enable(self, en) -> TestGen[None]:
        yield self.adapter.en.eq(1 if en else 0)

    def enable(self) -> TestGen[None]:
        yield from self.set_enable(True)

    def disable(self) -> TestGen[None]:
        yield from self.set_enable(False)

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

    def call_init(self, data: RecordValueDict = {}, /, **kwdata: ValueLike | RecordValueDict) -> TestGen[None]:
        if data and kwdata:
            raise TypeError("call_init() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
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

    def call_try(
        self, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict
    ) -> TestGen[Optional[RecordIntDictRet]]:
        if data and kwdata:
            raise TypeError("call_try() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        yield from self.call_init(data)
        yield
        outputs = yield from self.call_result()
        yield from self.disable()
        return outputs

    def call(self, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict) -> TestGen[RecordIntDictRet]:
        if data and kwdata:
            raise TypeError("call() takes either a single dict or keyword arguments")
        if not data:
            data = kwdata
        yield from self.call_init(data)
        yield
        return (yield from self.call_do())

    # Operations for Adapter

    def method_argument(self) -> TestGen[Optional[RecordIntDictRet]]:
        return (yield from self.call_result())

    def method_return(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from self.set_inputs(data)

    def method_handle(
        self,
        function: Callable[..., Optional[RecordIntDict]],
        *,
        enable: Optional[Callable[[], bool]] = None,
        extra_settle_count: int = 0,
    ) -> TestGen[None]:
        enable = enable or (lambda: True)
        yield from self.set_enable(enable())

        # One extra Settle() required to propagate enable signal.
        for _ in range(extra_settle_count + 1):
            yield Settle()
        while (arg := (yield from self.method_argument())) is None:
            yield
            yield from self.set_enable(enable())
            for _ in range(extra_settle_count + 1):
                yield Settle()

        ret_out = method_def_helper(self, function, **arg)
        yield from self.method_return(ret_out or {})
        yield

    def method_handle_loop(
        self,
        function: Callable[..., Optional[RecordIntDict]],
        *,
        enable: Optional[Callable[[], bool]] = None,
        extra_settle_count: int = 0,
    ) -> TestGen[None]:
        yield Passive()
        while True:
            yield from self.method_handle(function, enable=enable, extra_settle_count=extra_settle_count)

    # Debug signals

    def debug_signals(self) -> SignalBundle:
        return self.adapter.debug_signals()


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

        return mock

    return decorator
