import unittest
import random

from amaranth import *
from test.common import *
from coreblocks.utils import align_to_power_of_two, popcount
from parameterized import parameterized_class
from coreblocks.fu.divison.long_division import RecursiveDivison

class PopcountTestCircuit(Elaboratable):
    def __init__(self, size: int):
        self.divisor = Signal(size)
        self.dividend = Signal(size)
        self.quotient = Signal(size)
        self.reminder = Signal(size)
        self.size = size    

    def elaborate(self, platform):
        m = Module()

        m.submodules.div = div = RecursiveDivison(self.size, self.size)

        m.d.comb += div.dividend.eq(self.dividend)
        m.d.comb += div.divisor.eq(self.divisor)
        m.d.comb += div.inp.eq(0)
        
        m.d.comb += self.reminder.eq(div.reminder)
        m.d.comb += self.quotient.eq(div.quotient)

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        return m

class TestDiv(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 1
        self.size = 5
        self.m = PopcountTestCircuit(self.size)

    def check(self, d, r):
        yield self.m.dividend.eq(d)
        yield self.m.divisor.eq(r)
        yield Settle()
        reminder = yield self.m.reminder
        quotient = yield self.m.quotient

        print('=========')

        print(f'{d} / {r} = {quotient} rem {reminder}')

        if r != 0:
            self.assertEqual(d // r, quotient, f"")
            self.assertEqual(d % r, reminder, f"")
        else:
            self.assertEqual((1 << self.size) - 1, quotient, f"")
            self.assertEqual(d, reminder, f"")

    def process(self):
        yield from self.check(5, 3)
        yield from self.check(6, 7)
        yield from self.check(1, 1)
        yield from self.check(10, 2)
        yield from self.check(13, 7)
        yield from self.check(12, 5)
        yield from self.check(12, 0)

    def test_popcount(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.process)