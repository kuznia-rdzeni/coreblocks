import os
import random
import unittest
import functools
from enum import Enum
from contextlib import contextmanager, nullcontext
from typing import TypeVar, Generic, Type, TypeGuard, Any, Union, Callable, cast, TypeAlias
from abc import ABC
from amaranth import *
from amaranth.sim import *
from .testbenchio import TestbenchIO
from .functions import TestGen
from ..gtkw_extension import write_vcd_ext
from transactron import Method
from transactron.lib import AdapterTrans
from transactron.core import TransactionModule
from transactron.utils import ModuleConnector, HasElaborate, auto_debug_signals, HasDebugSignals

T = TypeVar("T")
_T_nested_collection: TypeAlias = T | list["_T_nested_collection[T]"] | dict[str, "_T_nested_collection[T]"]


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

        for name, attr in vars(self._dut).items():
            if guard_nested_collection(attr, Method) and attr:
                tb_cont, mc = transform_methods_to_testbenchios(attr)
                self._io[name] = tb_cont
                m.submodules[name] = mc

        return m

    def debug_signals(self):
        sigs = {"_dut": auto_debug_signals(self._dut)}
        for name, io in self._io.items():
            sigs[name] = auto_debug_signals(io)
        return sigs


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


class CoreblocksCommand(ABC):
    pass


class Now(CoreblocksCommand):
    pass


class TrueSettle(CoreblocksCommand):
    """Wait till all process are waiting for the next cycle or for the TrueSettle"""

    pass


class SyncProcessState(Enum):
    """State of SyncProcessWrapper."""

    sleeping = 0  # Wait for the next cycle
    running = 1
    ended = 2
    true_settle = 3  # Wait for the TrueSettle


class SyncProcessWrapper:
    def __init__(self, f):
        self.org_process = f
        self.current_cycle = 0
        self.state = None
        self.blocked = None

    def _wrapping_function(self):
        response = None
        org_coroutine = self.org_process()
        self.state = SyncProcessState.running
        try:
            while True:
                # call orginal test process and catch data yielded by it in `command` variable
                command = org_coroutine.send(response)
                # If process wait for new cycle
                if command is None:
                    self.current_cycle += 1
                    self.state = SyncProcessState.sleeping
                    # forward to amaranth
                    yield
                    self.state = SyncProcessState.running
                elif isinstance(command, CoreblocksCommand):
                    if isinstance(command, Now):
                        response = self.current_cycle
                    elif isinstance(command, TrueSettle):
                        self.state = SyncProcessState.true_settle
                        self.blocked = True
                        while self.blocked:
                            yield Settle()
                        self.state = SyncProcessState.running
                    else:
                        raise RuntimeError(f"Not known CoreblocksCommand: {command}")
                # Pass everything else to amaranth simulator without modifications
                else:
                    response = yield command
        except StopIteration:
            self.state = SyncProcessState.ended
            pass


class PysimSimulator(Simulator):
    def __init__(self, module: HasElaborate, max_cycles: float = 10e4, add_transaction_module=True, traces_file=None):
        test_module = TestModule(module, add_transaction_module)
        tested_module = test_module.tested_module
        super().__init__(test_module)

        clk_period = 1e-6
        self.add_clock(clk_period)

        if isinstance(tested_module, HasDebugSignals):
            extra_signals = tested_module.debug_signals
        else:
            extra_signals = functools.partial(auto_debug_signals, tested_module)

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
        self.sync_proc_list = []

    def add_sync_process(self, f: Callable[[], TestGen]):
        f_wrapped = SyncProcessWrapper(f)
        self.sync_proc_list.append(f_wrapped)
        super().add_sync_process(f_wrapped._wrapping_function)

    def _check_true_settle_ready(self):
        return all(p.state != SyncProcessState.running for p in self.sync_proc_list)

    def _unblock_sync_processes(self):
        for p in self.sync_proc_list:
            if p.blocked:
                p.blocked = False

    def run(self) -> bool:
        deadline = self.deadline * 1e12
        assert self._engine.now <= deadline
        last_now = self._engine.now
        while self.advance() and self._engine.now < deadline:
            if last_now == self._engine.now:
                if self._check_true_settle_ready():
                    self._unblock_sync_processes()
            last_now = self._engine.now
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

    def random_wait(self, max_cycle_cnt):
        """
        Wait for a random amount of cycles in range [1, max_cycle_cnt)
        """
        yield from self.tick(random.randrange(max_cycle_cnt))
