from unittest.mock import patch
from io import StringIO

from amaranth import *

from transactron import *
from transactron.testing import TestCaseWithSimulator
from transactron.lib import logging

log = logging.HardwareLogger("test")


class LogTest(Elaboratable):
    def __init__(self):
        self.input = Signal(range(100))
        self.counter = Signal(range(200))

    def elaborate(self, platform):
        m = TModule()

        with m.If(self.input == 42):
            log.warning(m, True, "Log triggered under Amaranth If value+3=0x{:x}", self.input + 3)

        log.warning(m, self.input[0] == 0, "Input is even! input={}, counter={}", self.input, self.counter)

        m.d.sync += self.counter.eq(self.counter + 1)

        return m


class ErrorLogTest(Elaboratable):
    def __init__(self):
        self.input = Signal()
        self.output = Signal()

    def elaborate(self, platform):
        m = TModule()

        m.d.comb += self.output.eq(self.input & ~self.input)

        log.error(
            m,
            self.input != self.output,
            "Input is different than output! input=0x{:x} output=0x{:x}",
            self.input,
            self.output,
        )

        return m


class AssertionTest(Elaboratable):
    def __init__(self):
        self.input = Signal()
        self.output = Signal()

    def elaborate(self, platform):
        m = TModule()

        m.d.comb += self.output.eq(self.input & ~self.input)

        log.assertion(m, self.input == self.output, "Output differs")

        return m


class TestLog(TestCaseWithSimulator):
    @patch("sys.stdout", new_callable=StringIO)
    def test_log(self, stdout):
        m = LogTest()

        def proc():
            for i in range(50):
                yield
                yield m.input.eq(i)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(proc)

        self.assertIn("Log triggered under Amaranth If value+3=0x2d", stdout.getvalue())
        for i in range(0, 50, 2):
            self.assertIn(f"Input is even! input={i}, counter={i + 2}", stdout.getvalue())

    @patch("sys.stdout", new_callable=StringIO)
    def test_error_log(self, stdout):
        m = ErrorLogTest()

        def proc():
            yield
            yield m.input.eq(1)

        with self.assertRaises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)

        extected_out = "Input is different than output! input=0x1 output=0x0"
        self.assertIn(extected_out, stdout.getvalue())

    @patch("sys.stdout", new_callable=StringIO)
    def test_assertion(self, stdout):
        m = AssertionTest()

        def proc():
            yield
            yield m.input.eq(1)

        with self.assertRaises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)

        extected_out = "Output differs"
        self.assertIn(extected_out, stdout.getvalue())
