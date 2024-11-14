from amaranth import *

from transactron import Method, def_method, TModule

from transactron.testing import TestCaseWithSimulator, data_layout, SimpleTestCircuit, TestbenchContext
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector


class Echo(Elaboratable):
    def __init__(self):
        self.data_bits = 8

        self.layout_in = data_layout(self.data_bits)
        self.layout_out = data_layout(self.data_bits)

        self.action = Method(i=self.layout_in, o=self.layout_out)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.action, ready=C(1))
        def _(arg):
            return arg

        return m


class Consumer(Elaboratable):
    def __init__(self):
        self.data_bits = 8

        self.layout_in = data_layout(self.data_bits)
        self.layout_out = []

        self.action = Method(i=self.layout_in, o=self.layout_out)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.action, ready=C(1))
        def _(arg):
            return None

        return m


class TestAdapterTrans(TestCaseWithSimulator):
    async def proc(self, sim: TestbenchContext):
        for _ in range(3):
            await self.consumer.action.call(sim, data=0)
        for expected in [4, 1, 0]:
            obtained = (await self.echo.action.call(sim, data=expected)).data
            assert expected == obtained

    def test_single(self):
        self.echo = SimpleTestCircuit(Echo())
        self.consumer = SimpleTestCircuit(Consumer())
        self.m = ModuleConnector(echo=self.echo, consumer=self.consumer)

        with self.run_simulation(self.m, max_cycles=100) as sim:
            sim.add_testbench(self.proc)
