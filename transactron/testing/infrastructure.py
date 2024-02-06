import sys
import os
import random
import unittest
import functools
from contextlib import contextmanager, nullcontext
from typing import TypeVar, Generic, Type, TypeGuard, Any, Union, Callable, cast, TypeAlias
from abc import ABC
from amaranth import *
from amaranth.sim import *

from transactron.utils.dependencies import DependencyContext, DependencyManager
from .testbenchio import TestbenchIO
from .profiler import profiler_process, Profile
from .functions import TestGen
from .assertion import make_assert_handler
from .gtkw_extension import write_vcd_ext
from transactron import Method
from transactron.lib import AdapterTrans
from transactron.core import TransactionManagerKey, TransactionModule
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
        try:
            return self._io[name]
        except KeyError:
            raise AttributeError(f"No mock for '{name}'")

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


class _TestModule(Elaboratable):
    def __init__(self, tested_module: HasElaborate, add_transaction_module: bool):
        self.tested_module = (
            TransactionModule(tested_module, dependency_manager=DependencyContext.get())
            if add_transaction_module
            else tested_module
        )
        self.add_transaction_module = add_transaction_module

    def elaborate(self, platform) -> HasElaborate:
        m = Module()

        # so that Amaranth allows us to use add_clock
        _dummy = Signal()
        m.d.sync += _dummy.eq(1)

        m.submodules.tested_module = self.tested_module

        m.domains.sync_neg = ClockDomain(clk_edge="neg", local=True)

        return m


class CoreblocksCommand(ABC):
    pass


class Now(CoreblocksCommand):
    pass


class SyncProcessWrapper:
    def __init__(self, f):
        self.org_process = f
        self.current_cycle = 0

    def _wrapping_function(self):
        response = None
        org_coroutine = self.org_process()
        try:
            while True:
                # call orginal test process and catch data yielded by it in `command` variable
                command = org_coroutine.send(response)
                # If process wait for new cycle
                if command is None:
                    self.current_cycle += 1
                    # forward to amaranth
                    yield
                elif isinstance(command, Now):
                    response = self.current_cycle
                # Pass everything else to amaranth simulator without modifications
                else:
                    response = yield command
        except StopIteration:
            pass


class PysimSimulator(Simulator):
    def __init__(
        self,
        module: HasElaborate,
        max_cycles: float = 10e4,
        add_transaction_module=True,
        traces_file=None,
        clk_period=1e-6,
    ):
        test_module = _TestModule(module, add_transaction_module)
        self.tested_module = tested_module = test_module.tested_module
        super().__init__(test_module)

        self.add_clock(clk_period)
        self.add_clock(clk_period, domain="sync_neg")

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

    def add_sync_process(self, f: Callable[[], TestGen]):
        f_wrapped = SyncProcessWrapper(f)
        super().add_sync_process(f_wrapped._wrapping_function)

    def run(self) -> bool:
        with self.ctx:
            self.run_until(self.deadline)

        return not self.advance()


class TestCaseWithSimulator(unittest.TestCase):
    dependency_manager: DependencyManager

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dependency_manager = DependencyManager()

        def wrap(f: Callable[[], None]):
            @functools.wraps(f)
            def wrapper():
                with DependencyContext(self.dependency_manager):
                    f()

            return wrapper

        for k in dir(self):
            if k.startswith("test"):
                f = getattr(self, k)
                if isinstance(f, Callable):
                    setattr(self, k, wrap(getattr(self, k)))

    def add_class_mocks(self, sim: PysimSimulator) -> None:
        for key in dir(self):
            val = getattr(self, key)
            if hasattr(val, "_transactron_testing_process"):
                sim.add_sync_process(val)

    def add_local_mocks(self, sim: PysimSimulator, frame_locals: dict) -> None:
        for key, val in frame_locals.items():
            if hasattr(val, "_transactron_testing_process"):
                sim.add_sync_process(val)

    def add_all_mocks(self, sim: PysimSimulator, frame_locals: dict) -> None:
        self.add_class_mocks(sim)
        self.add_local_mocks(sim, frame_locals)

    @contextmanager
    def run_simulation(self, module: HasElaborate, max_cycles: float = 10e4, add_transaction_module=True):
        traces_file = None
        if "__COREBLOCKS_DUMP_TRACES" in os.environ:
            traces_file = unittest.TestCase.id(self)

        clk_period = 1e-6
        sim = PysimSimulator(
            module,
            max_cycles=max_cycles,
            add_transaction_module=add_transaction_module,
            traces_file=traces_file,
            clk_period=clk_period,
        )
        self.add_all_mocks(sim, sys._getframe(2).f_locals)

        yield sim

        profile = None
        if "__TRANSACTRON_PROFILE" in os.environ and isinstance(sim.tested_module, TransactionModule):
            profile = Profile()
            sim.add_sync_process(
                profiler_process(sim.tested_module.manager.get_dependency(TransactionManagerKey()), profile)
            )

        sim.add_sync_process(make_assert_handler(self.assertTrue))

        res = sim.run()

        if profile is not None:
            profile_dir = "test/__profiles__"
            profile_file = unittest.TestCase.id(self)
            os.makedirs(profile_dir, exist_ok=True)
            profile.encode(f"{profile_dir}/{profile_file}.json")

        self.assertTrue(res, "Simulation time limit exceeded")

    def tick(self, cycle_cnt: int = 1):
        """
        Yields for the given number of cycles.
        """

        for _ in range(cycle_cnt):
            yield

    def random_wait(self, max_cycle_cnt: int, *, min_cycle_cnt: int = 0):
        """
        Wait for a random amount of cycles in range [min_cycle_cnt, max_cycle_cnt]
        """
        yield from self.tick(random.randrange(min_cycle_cnt, max_cycle_cnt + 1))

    def random_wait_geom(self, prob: float = 0.5):
        """
        Wait till the first success, where there is `prob` probability for success in each cycle.
        """
        while random.random() > prob:
            yield
