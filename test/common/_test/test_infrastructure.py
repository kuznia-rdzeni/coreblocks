from amaranth import *
from amaranth.sim import Settle
from test.common import *


class EmptyCircuit(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()
        return m


class TestNow(TestCaseWithSimulator):
    def setUp(self):
        self.test_cycles = 10
        self.m = SimpleTestCircuit(EmptyCircuit())

    def process(self):
        for k in range(self.test_cycles):
            now = yield Now()
            assert k == now
            # check if second call don't change the returned value
            now = yield Now()
            assert k == now

            yield

    def test_random(self):
        with self.run_simulation(self.m, 50) as sim:
            sim.add_sync_process(self.process)


class TestFork(TestCaseWithSimulator):
    def setUp(self):
        self.m = SimpleTestCircuit(EmptyCircuit())
        self.data = 0

    def subproces(self):
        self.assertEqual(self.data, 0)
        self.data = 1
        yield
        yield
        self.assertEqual(self.data, 2)

    def process(self):
        yield Fork(self.subproces)
        yield
        yield Settle()
        self.assertEqual(self.data, 1)
        self.data = 2

    def test(self):
        with self.run_simulation(self.m, 20) as sim:
            sim.add_sync_process(self.process)
