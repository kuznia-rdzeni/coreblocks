import pytest
from itertools import product
from typing import Optional
from amaranth import *
from amaranth.sim import *
from transactron.testing.method_mock import MethodMock, def_method_mock
from transactron.testing.testbenchio import TestbenchIO

from transactron.utils import ModuleConnector

from transactron.testing import SimpleTestCircuit, TestCaseWithSimulator, TestbenchContext

from transactron import *
from transactron.lib import Adapter, Connect, ConnectTrans


def empty_method(m: TModule, method: Method):
    @def_method(m, method)
    def _():
        pass


class SimultaneousDiamondTestCircuit(Elaboratable):
    def __init__(self):
        self.method_l = Method()
        self.method_r = Method()
        self.method_u = Method()
        self.method_d = Method()

    def elaborate(self, platform):
        m = TModule()

        empty_method(m, self.method_l)
        empty_method(m, self.method_r)
        empty_method(m, self.method_u)
        empty_method(m, self.method_d)

        # the only possibilities for the following are: (l, u, r) or (l, d, r)
        self.method_l.simultaneous_alternatives(self.method_u, self.method_d)
        self.method_r.simultaneous_alternatives(self.method_u, self.method_d)

        return m


class TestSimultaneousDiamond(TestCaseWithSimulator):
    def test_diamond(self):
        circ = SimpleTestCircuit(SimultaneousDiamondTestCircuit())

        async def process(sim: TestbenchContext):
            methods = {"l": circ.method_l, "r": circ.method_r, "u": circ.method_u, "d": circ.method_d}
            for i in range(1 << len(methods)):
                enables: dict[str, bool] = {}
                for k, n in enumerate(methods):
                    enables[n] = bool(i & (1 << k))
                    methods[n].set_enable(sim, enables[n])
                dones: dict[str, bool] = {}
                for n in methods:
                    dones[n] = bool(methods[n].get_done(sim))
                await sim.tick()
                for n in methods:
                    if not enables[n]:
                        assert not dones[n]
                if enables["l"] and enables["r"] and (enables["u"] or enables["d"]):
                    assert dones["l"]
                    assert dones["r"]
                    assert dones["u"] or dones["d"]
                else:
                    assert not any(dones.values())

        with self.run_simulation(circ) as sim:
            sim.add_testbench(process)


class UnsatisfiableTriangleTestCircuit(Elaboratable):
    def __init__(self):
        self.method_l = Method()
        self.method_u = Method()
        self.method_d = Method()

    def elaborate(self, platform):
        m = TModule()

        empty_method(m, self.method_l)
        empty_method(m, self.method_u)
        empty_method(m, self.method_d)

        # the following is unsatisfiable
        self.method_l.simultaneous_alternatives(self.method_u, self.method_d)
        self.method_u.simultaneous(self.method_d)

        return m


class TestUnsatisfiableTriangle(TestCaseWithSimulator):
    def test_unsatisfiable(self):
        circ = SimpleTestCircuit(UnsatisfiableTriangleTestCircuit())

        with pytest.raises(RuntimeError):
            with self.run_simulation(circ) as _:
                pass


class HelperConnect(Elaboratable):
    def __init__(self, source: Method, target: Method, request: Signal, data: int):
        self.source = source
        self.target = target
        self.request = request
        self.data = data

    def elaborate(self, platform):
        m = TModule()

        with Transaction().body(m, request=self.request):
            self.target(m, self.data ^ self.source(m).data)

        return m


class TransitivityTestCircuit(Elaboratable):
    def __init__(self, target: Method, req1: Signal, req2: Signal):
        self.source1 = Method(i=[("data", 2)])
        self.source2 = Method(i=[("data", 2)])
        self.target = target
        self.req1 = req1
        self.req2 = req2

    def elaborate(self, platform):
        m = TModule()

        m.submodules.c1 = c1 = Connect([("data", 2)])
        m.submodules.c2 = c2 = Connect([("data", 2)])
        self.source1.proxy(m, c1.write)
        self.source2.proxy(m, c1.write)
        m.submodules.ct = ConnectTrans(c2.read, self.target)
        m.submodules.hc1 = HelperConnect(c1.read, c2.write, self.req1, 1)
        m.submodules.hc2 = HelperConnect(c1.read, c2.write, self.req2, 2)

        return m


class TestTransitivity(TestCaseWithSimulator):
    def test_transitivity(self):
        target = TestbenchIO(Adapter(i=[("data", 2)]))
        req1 = Signal()
        req2 = Signal()

        circ = SimpleTestCircuit(TransitivityTestCircuit(target.adapter.iface, req1, req2))
        m = ModuleConnector(test_circuit=circ, target=target)

        result: Optional[int]

        @def_method_mock(lambda: target)
        def target_process(data: int):
            @MethodMock.effect
            def eff():
                nonlocal result
                result = data

        async def process(sim: TestbenchContext):
            nonlocal result
            for source, data, reqv1, reqv2 in product([circ.source1, circ.source2], [0, 1, 2, 3], [0, 1], [0, 1]):
                result = None
                sim.set(req1, reqv1)
                sim.set(req2, reqv2)
                call_result = await source.call_try(sim, data=data)

                if not reqv1 and not reqv2:
                    assert call_result is None
                    assert result is None
                else:
                    assert call_result is not None
                    possibles = reqv1 * [data ^ 1] + reqv2 * [data ^ 2]
                    assert result in possibles

        with self.run_simulation(m) as sim:
            sim.add_testbench(process)
