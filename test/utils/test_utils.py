import unittest
import random

from amaranth import *
from test.common import *
from coreblocks.utils import align_to_power_of_two, popcount
from parameterized import parameterized_class


class TestAlignToPowerOfTwo(unittest.TestCase):
    def test_align_to_power_of_two(self):
        test_cases = [
            (2, 2, 4),
            (2, 1, 2),
            (3, 1, 4),
            (7, 3, 8),
            (8, 3, 8),
            (14, 3, 16),
            (17, 3, 24),
            (33, 3, 40),
            (33, 1, 34),
            (33, 0, 33),
            (33, 4, 48),
            (33, 5, 64),
            (33, 6, 64),
        ]

        for num, power, expected in test_cases:
            out = align_to_power_of_two(num, power)
            self.assertEqual(expected, out)


class PopcountTestCircuit(Elaboratable):
    def __init__(self, size: int):
        self.sig_in = Signal(size)
        self.sig_out = Signal(size)

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.sig_out.eq(popcount(self.sig_in))
        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        return m


@parameterized_class(
    ("name", "size"),
    [("size" + str(s), s) for s in [2, 3, 4, 5, 6, 8, 10, 16, 21, 32, 33, 64, 1025]],
)
class TestPopcount(TestCaseWithSimulator):
    size: int

    def setUp(self):
        random.seed(14)
        self.test_number = 40
        self.m = PopcountTestCircuit(self.size)

    def check(self, n):
        yield self.m.sig_in.eq(n)
        yield Settle()
        out_popcount = yield self.m.sig_out
        self.assertEqual(out_popcount, n.bit_count(), f"{n:x}")

    def process(self):
        for i in range(self.test_number):
            n = random.randrange(2**self.size)
            yield from self.check(n)
        yield from self.check(2**self.size - 1)

    def test_popcount(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.process)
