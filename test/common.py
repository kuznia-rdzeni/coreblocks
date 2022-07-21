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
from coreblocks._typing import ValueLike
from .gtkw_extension import write_vcd_ext


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

    def enable(self) -> TestGen[None]:
        yield self.adapter.en.eq(1)

    def disable(self) -> TestGen[None]:
        yield self.adapter.en.eq(0)

    def done(self) -> TestGen[int]:
        return (yield self.adapter.done)

    def _wait_until_done(self) -> TestGen[None]:
        while (yield self.adapter.done) != 1:
            yield

    def call_init(self, data: RecordValueDict = {}) -> TestGen[None]:
        yield from self.enable()
        yield from set_inputs(data, self.adapter.data_in)

    def call_result(self) -> TestGen[Optional[RecordIntDictRet]]:
        if (yield self.adapter.done):
            return (yield from get_outputs(self.adapter.data_out))
        return None

    def call_do(self) -> TestGen[RecordIntDict]:
        while (outputs := (yield from self.call_result())) is None:
            yield
        yield from self.disable()
        return outputs

    def call(self, data: RecordIntDict = {}) -> TestGen[RecordIntDictRet]:
        yield from self.call_init(data)
        yield
        return (yield from self.call_do())

    def debug_signals(self) -> DebugSignals:
        return self.adapter.debug_signals()
