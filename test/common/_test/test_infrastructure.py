from amaranth import *
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


class TestTrueSettle(TestCaseWithSimulator):
    def setUp(self):
        self.m = SimpleTestCircuit(EmptyCircuit())
        self.test_cycles = 10
        self.flag = False
        random.seed(14)

    def true_settle_process(self):
        for k in range(self.test_cycles):
            yield TrueSettle()
            self.assertTrue(self.flag)
            self.flag = False
            yield

    def flag_process(self):
        for k in range(self.test_cycles):
            for i in range(random.randrange(0, 5)):
                yield Settle()
            self.flag = True
            yield

    def test_flag(self):
        with self.run_simulation(self.m, 50) as sim:
            sim.add_sync_process(self.true_settle_process)
            sim.add_sync_process(self.flag_process)
