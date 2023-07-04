import unittest
import random

from amaranth import *
from test.common import *
from coreblocks.utils import (
    align_to_power_of_two,
    popcount,
    count_leading_zeros,
    count_trailing_zeros,
    MultiPriorityEncoder,
)
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


class CLZTestCircuit(Elaboratable):
    def __init__(self, xlen_log: int):
        self.sig_in = Signal(1 << xlen_log)
        self.sig_out = Signal(xlen_log + 1)
        self.xlen_log = xlen_log

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.sig_out.eq(count_leading_zeros(self.sig_in))
        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        return m


@parameterized_class(
    ("name", "size"),
    [("size" + str(s), s) for s in range(1, 7)],
)
class TestCountLeadingZeros(TestCaseWithSimulator):
    size: int

    def setUp(self):
        random.seed(14)
        self.test_number = 40
        self.m = CLZTestCircuit(self.size)

    def check(self, n):
        yield self.m.sig_in.eq(n)
        yield Settle()
        out_clz = yield self.m.sig_out
        self.assertEqual(out_clz, (2**self.size) - n.bit_length(), f"{n:x}")

    def process(self):
        for i in range(self.test_number):
            n = random.randrange(2**self.size)
            yield from self.check(n)
        yield from self.check(2**self.size - 1)

    def test_count_leading_zeros(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.process)


class CTZTestCircuit(Elaboratable):
    def __init__(self, xlen_log: int):
        self.sig_in = Signal(1 << xlen_log)
        self.sig_out = Signal(xlen_log + 1)
        self.xlen_log = xlen_log

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.sig_out.eq(count_trailing_zeros(self.sig_in))
        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        return m


@parameterized_class(
    ("name", "size"),
    [("size" + str(s), s) for s in range(1, 7)],
)
class TestCountTrailingZeros(TestCaseWithSimulator):
    size: int

    def setUp(self):
        random.seed(14)
        self.test_number = 40
        self.m = CTZTestCircuit(self.size)

    def check(self, n):
        yield self.m.sig_in.eq(n)
        yield Settle()
        out_ctz = yield self.m.sig_out

        expected = 0
        if n == 0:
            expected = 2**self.size
        else:
            while (n & 1) == 0:
                expected += 1
                n >>= 1

        self.assertEqual(out_ctz, expected, f"{n:x}")

    def process(self):
        for i in range(self.test_number):
            n = random.randrange(2**self.size)
            yield from self.check(n)
        yield from self.check(2**self.size - 1)

    def test_count_trailing_zeros(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.process)


class TestMultiPriorityEncoder(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 50
        self.input_width = 16
        self.output_count = 4

        self.circ = MultiPriorityEncoder(self.input_width, self.output_count)

    def get_expected(self, input):
        places = []
        for i in range(self.input_width):
            if input % 2:
                places.append(i)
            input //= 2
        places += [None] * self.output_count
        return places

    def process(self):
        for _ in range(self.test_number):
            input = random.randrange(2**self.input_width)
            yield self.circ.input.eq(input)
            yield Settle()
            expected_output = self.get_expected(input)
            for ex, real, valid in zip(expected_output, self.circ.outputs, self.circ.valids):
                if ex is None:
                    self.assertEqual((yield valid), 0)
                else:
                    self.assertEqual((yield valid), 1)
                    self.assertEqual((yield real), ex)

    def test_random(self):
        with self.run_simulation(self.circ, max_cycles=100) as sim:
            sim.add_process(self.process)
