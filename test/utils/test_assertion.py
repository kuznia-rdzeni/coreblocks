from amaranth import *

from transactron.utils import assertion
from transactron.testing import TestCaseWithSimulator


class AssertionTest(Elaboratable):
    def __init__(self):
        self.input = Signal()
        self.output = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.output.eq(self.input & ~self.input)

        assertion(self.input == self.output)

        return m


class TestAssertion(TestCaseWithSimulator):
    def test_assertion(self):
        m = AssertionTest()

        def proc():
            yield
            yield m.input.eq(1)

        with self.assertRaises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)
