from itertools import product
from typing import Optional
from amaranth import *
from amaranth.sim import *

from coreblocks.utils.utils import ModuleConnector

from ..common import SimpleTestCircuit, TestCaseWithSimulator, TestbenchIO, def_method_mock

from coreblocks.transactions import *
from coreblocks.transactions.lib import Adapter, condition


class SimultaneousDiamondTestCircuit(Elaboratable):
    def __init__(self):
        self.method_l = Method()
        self.method_r = Method()
        self.method_u = Method()
        self.method_d = Method()

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.method_l)
        def _():
            pass

        @def_method(m, self.method_r)
        def _():
            pass

        @def_method(m, self.method_u)
        def _():
            pass

        @def_method(m, self.method_d)
        def _():
            pass

        # the only possibilities for the following are: (l, u, r) or (l, d, r)
        self.method_l.simultaneous_groups([self.method_u], [self.method_d])
        self.method_r.simultaneous_groups([self.method_u], [self.method_d])

        return m


class SimultaneousDiamondTest(TestCaseWithSimulator):
    def test_diamond(self):
        circ = SimpleTestCircuit(SimultaneousDiamondTestCircuit())

        def process():
            methods = {"l": circ.method_l, "r": circ.method_r, "u": circ.method_u, "d": circ.method_d}
            for i in range(1 << len(methods)):
                enables: dict[str, bool] = {}
                for k, n in enumerate(methods):
                    enables[n] = bool(i & (1 << k))
                    yield from methods[n].set_enable(enables[n])
                yield
                dones: dict[str, bool] = {}
                for n in methods:
                    dones[n] = bool((yield from methods[n].done()))
                for n in methods:
                    if not enables[n]:
                        self.assertFalse(dones[n])
                if enables["l"] and enables["r"] and (enables["u"] or enables["d"]):
                    self.assertTrue(dones["l"])
                    self.assertTrue(dones["r"])
                    self.assertTrue(dones["u"] or dones["d"])
                else:
                    self.assertFalse(any(dones.values()))

        with self.run_simulation(circ) as sim:
            sim.add_sync_process(process)


class ConditionTestCircuit(Elaboratable):
    def __init__(self, target: Method):
        self.target = target
        self.source = Method(i=[("cond1", 1), ("cond2", 1), ("cond3", 1)])

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.source)
        def _(cond1, cond2, cond3):
            with condition(m) as branch:
                with branch(cond1):
                    self.target(m, cond=1)
                with branch(cond2):
                    self.target(m, cond=2)
                with branch(cond3):
                    self.target(m, cond=3)
                with branch():
                    self.target(m, cond=0)

        return m


class ConditionTest(TestCaseWithSimulator):
    def test_condition(self):
        target = TestbenchIO(Adapter(i=[("cond", 2)]))

        circ = SimpleTestCircuit(ConditionTestCircuit(target.adapter.iface))
        m = ModuleConnector(test_circuit=circ, target=target)

        selection: Optional[int]

        @def_method_mock(lambda: target)
        def target_process(cond):
            nonlocal selection
            selection = cond

        def process():
            nonlocal selection
            for c1, c2, c3 in product([0, 1], [0, 1], [0, 1]):
                selection = None
                yield from circ.source.call(cond1=c1, cond2=c2, cond3=c3)
                self.assertEqual(selection, c1 + 2 * c2 * (1 - c1) + 3 * c3 * (1 - c2) * (1 - c1))

        with self.run_simulation(m) as sim:
            sim.add_sync_process(target_process)
            sim.add_sync_process(process)
