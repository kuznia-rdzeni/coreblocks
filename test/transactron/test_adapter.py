from amaranth import *

from transactron import Method, def_method, TModule


from transactron.testing import TestCaseWithSimulator, data_layout, SimpleTestCircuit, ModuleConnector


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
    def proc(self):
        for _ in range(3):
            # this would previously timeout if the output layout was empty (as is in this case)
            yield from self.consumer.action.call(data=0)
        for expected in [4, 1, 0]:
            obtained = (yield from self.echo.action.call(data=expected))["data"]
            assert expected == obtained

    def test_single(self):
        self.echo = SimpleTestCircuit(Echo())
        self.consumer = SimpleTestCircuit(Consumer())
        self.m = ModuleConnector(echo=self.echo, consumer=self.consumer)

        with self.run_simulation(self.m, max_cycles=100) as sim:
            sim.add_process(self.proc)
