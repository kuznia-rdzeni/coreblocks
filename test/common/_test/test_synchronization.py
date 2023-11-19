from amaranth import *
from test.common import *
from test.common.synchronization import *


class EmptyCircuit(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()
        return m


class TestCondVar(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_count = 50
        self.m = SimpleTestCircuit(EmptyCircuit())
        self.value = 0
        self.cv = CondVar()

    def random_settles(self):
        for i in range(3):
            yield Settle()

    def process1(self):
        yield
        yield
        yield
        self.value = 1
        yield from self.random_settles()
        yield from self.cv.notify_all()
        yield from self.cv.wait()
        yield from self.random_settles()
        self.assertEqual(self.value, 2)

    def process2(self):
        yield from self.cv.wait()
        yield from self.random_settles()
        self.assertEqual(self.value, 1)
        self.value = 2
        yield from self.random_settles()
        yield from self.cv.notify_all()

    def test_random(self):
        for i in range(self.test_count):
            with self.run_simulation(self.m, 10) as sim:
                sim.add_sync_process(self.process1)
                sim.add_sync_process(self.process2)
