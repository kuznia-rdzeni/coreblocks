import unittest
from contextlib import contextmanager

from amaranth import *
from amaranth.sim import *


class TestCaseWithSimulator(unittest.TestCase):
    @contextmanager
    def runSimulation(self, module):
        sim = Simulator(module)
        yield sim
        with sim.write_vcd("test.vcd", "test.gtkw"):
            sim.run()
