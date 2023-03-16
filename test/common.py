import unittest
import os
import functools
from contextlib import contextmanager, nullcontext
from typing import Callable, Generic, Mapping, Union, Generator, TypeVar, Optional, Any, cast

from amaranth import *
from amaranth.hdl.ast import Statement
from amaranth.sim import *
from amaranth.sim.core import Command

from coreblocks.params import GenParams
from coreblocks.stages.rs_func_block import RSBlockComponent
from coreblocks.transactions.core import DebugSignals, Method, TransactionModule
from coreblocks.transactions.lib import AdapterBase, AdapterTrans
from coreblocks.utils import ValueLike, HasElaborate, HasDebugSignals, auto_debug_signals, LayoutLike
from .gtkw_extension import write_vcd_ext


T = TypeVar("T")
RecordValueDict = Mapping[str, Union[ValueLike, "RecordValueDict"]]
RecordIntDict = Mapping[str, Union[int, "RecordIntDict"]]
RecordIntDictRet = Mapping[str, Any]  # full typing hard to work with
TestGen = Generator[Command | Value | Statement | None, Any, T]


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


_T_HasElaborate = TypeVar("_T_HasElaborate", bound=HasElaborate)


class SimpleTestCircuit(Elaboratable, Generic[_T_HasElaborate]):
    def __init__(self, dut: _T_HasElaborate):
        self._dut = dut
        self._io = dict[str, TestbenchIO]()

    def __getattr__(self, name: str):
        return self._io[name]

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        dummy = Signal()
        m.d.sync += dummy.eq(1)

        m.submodules.dut = self._dut

        for name, attr in [(name, getattr(self._dut, name)) for name in dir(self._dut)]:
            if isinstance(attr, Method):
                self._io[name] = TestbenchIO(AdapterTrans(attr))
                m.submodules += self._io[name]

        return tm

    def debug_signals(self):
        return [io.debug_signals() for io in self._io.values()]


class TestCaseWithSimulator(unittest.TestCase):
    @contextmanager
    def run_simulation(self, module: HasElaborate, max_cycles: float = 10e4):
        test_name = unittest.TestCase.id(self)
        clk_period = 1e-6

        if isinstance(module, HasDebugSignals):
            extra_signals = module.debug_signals
        else:
            extra_signals = functools.partial(auto_debug_signals, module)

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

    def call_try(self, data: RecordIntDict = {}, /, **kwdata: int | RecordIntDict) -> TestGen[Optional[RecordIntDictRet]]:
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
            raise TypeError("call_try() takes either a single dict or keyword arguments")
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


def def_method_mock(
    tb_getter: Callable[[], TestbenchIO], **kwargs
) -> Callable[[Callable[[RecordIntDictRet], Optional[RecordIntDict]]], Callable[[], TestGen[None]]]:
    """
    Decorator function to create method mock handlers. It should be applied on
    a function which describes functionality which we want to invoke on method call.
    Such function will be wrapped by `method_handle_loop` and called on each
    method invocation.

    Use to wrap plain functions, not class methods. For wrapping class methods please
    see `def_class_method_mock`.

    Function `f` should take only one argument - data used in function invocation - and
    should return data which will be sent as response to method call.

    Please remember that decorators are fully evaluated when function is defined.

    Parameters
    ----------
    tbb_getter : Callable[[], TestbenchIO]
        Function which will be called to get TestbenchIO from which `method_handle_loop`
        should be used.
    **kwargs
        Arguments passed to `method_handle_loop`.

    Example
    -------
    ```
    m = TestCircuit()
    def target_process(k: int):
        @def_method_mock(lambda: m.target[k], settle=1, enable=False)
        def process(v):
            return {"data": v["data"] + k}
        return process
    ```
    """

    def decorator(func: Callable[[RecordIntDictRet], Optional[RecordIntDict]]) -> Callable[[], TestGen[None]]:
        @functools.wraps(func)
        def mock() -> TestGen[None]:
            tb = tb_getter()
            f = func
            assert isinstance(tb, TestbenchIO)
            yield from tb.method_handle_loop(f, **kwargs)

        return mock

    return decorator


def def_class_method_mock(
    tb_getter: Callable[[Any], TestbenchIO], **kwargs
) -> Callable[[Callable[[Any, RecordIntDictRet], Optional[RecordIntDict]]], Callable[[Any], TestGen[None]]]:
    """
    Decorator function to create method mock handlers. It should be applied on
    a function which describe functionality which we wan't to invoke on method call.
    Such function will be wrapped by `method_handle_loop` and called on each
    method invocation.

    Use to wrap class methods, not functions. For wrapping plain functions please
    see `def_method_mock`.

    Function `f` should take two arguments `self` and data which will be passed on
    to invoke a method. This function should return data which will be sent
    as response to method call.

    Make sure to defer accessing state, since decorators are evaluated eagerly
    during function declaration.

    Parameters
    ----------
    tb_getter : Callable[[self], TestbenchIO]
        Function which will be called to get TestbenchIO from which `method_handle_loop`
        should be used. That function should take only one argument - `self`.
    **kwargs
        Arguments passed to `method_handle_loop`.

    Example
    -------
    ```
    @def_class_method_mock(lambda self: self.m.target, settle=1)
    def target(self, v):
        return {"data": v["data"] + 1}
    ```
    """

    def decorator(func: Callable[[Any, RecordIntDictRet], Optional[RecordIntDict]]):
        @functools.wraps(func)
        def mock(self) -> TestGen[None]:
            def partial_func(x):
                return func(self, x)

            tb = tb_getter(self)
            assert isinstance(tb, TestbenchIO)
            yield from tb.method_handle_loop(partial_func, **kwargs)

        return mock

    return decorator


def test_gen_params(
    isa_str: str,
    *,
    phys_regs_bits: int = 7,
    rob_entries_bits: int = 7,
    start_pc: int = 0,
    rs_entries: int = 4,
    rs_block_number: int = 2,
):
    return GenParams(
        isa_str,
        func_units_config=[RSBlockComponent([], rs_entries=rs_entries) for _ in range(rs_block_number)],
        phys_regs_bits=phys_regs_bits,
        rob_entries_bits=rob_entries_bits,
        start_pc=start_pc,
    )
