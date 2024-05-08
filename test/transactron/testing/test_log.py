import pytest
from amaranth import *

from transactron import *
from transactron.testing import TestCaseWithSimulator
from transactron.lib import logging

LOGGER_NAME = "test_logger"

log = logging.HardwareLogger(LOGGER_NAME)


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
    def test_log(self, caplog):
        m = LogTest()

        def proc():
            for i in range(50):
                yield
                yield m.input.eq(i)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(proc)

        print(caplog.text)
        assert (
            "WARNING  test_logger:logging.py:83 [test/transactron/testing/test_log.py:22] "
            + "Log triggered under Amaranth If value+3=0x2d"
            in caplog.text
        )
        for i in range(0, 50, 2):
            expected_msg = (
                "WARNING  test_logger:logging.py:83 [test/transactron/testing/test_log.py:24] "
                + f"Input is even! input={i}, counter={i + 2}"
            )
            assert expected_msg in caplog.text

    def test_error_log(self, caplog):
        m = ErrorLogTest()

        def proc():
            yield
            yield m.input.eq(1)

        with pytest.raises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)

        extected_out = (
            "ERROR    test_logger:logging.py:83 [test/transactron/testing/test_log.py:41] "
            + "Input is different than output! input=0x1 output=0x0"
        )
        assert extected_out in caplog.text

    def test_assertion(self, caplog):
        m = AssertionTest()

        def proc():
            yield
            yield m.input.eq(1)

        with pytest.raises(AssertionError):
            with self.run_simulation(m) as sim:
                sim.add_sync_process(proc)

        extected_out = "ERROR    test_logger:logging.py:83 [test/transactron/testing/test_log.py:62] Output differs"
        assert extected_out in caplog.text
