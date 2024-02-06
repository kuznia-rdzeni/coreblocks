from amaranth import *

from transactron.utils import assertion
from transactron.utils.dependencies import DependencyManager
from transactron.testing import TestCaseWithSimulator


class AssertionTest(Elaboratable):
    def __init__(self, dependency_manager: DependencyManager):
        self.dependency_manager = dependency_manager
        self.input = Signal()
        self.output = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.output.eq(self.input & ~self.input)

        assertion(self.input == self.output)

        return m


class TestAssertion(TestCaseWithSimulator):
    def setUp(self):
        self.dependency_manager = DependencyManager()

    def test_assertion(self):
        m = AssertionTest(self.dependency_manager)

        def proc():
            yield
            yield m.input.eq(1)

        with self.assertRaises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)
