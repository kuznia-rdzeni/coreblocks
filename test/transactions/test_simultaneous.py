from amaranth import *
from amaranth.sim import *

from ..common import SimpleTestCircuit, TestCaseWithSimulator

from coreblocks.transactions import *
from coreblocks.transactions.lib import *


class SimultaneousDiamondTestCircuit(Elaboratable):
    def __init__(self):
        self.method_l = Method()
        self.method_r = Method()
        self.method_u = Method()
        self.method_d = Method()

    def elaborate(self, platform):
        m = Module()

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
