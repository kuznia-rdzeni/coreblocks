from amaranth import *
from amaranth.sim import *

from transactron.utils import OneHotSwitch

from transactron.testing import TestCaseWithSimulator

from parameterized import parameterized


class OneHotSwitchCircuit(Elaboratable):
    def __init__(self, width: int, test_zero: bool):
        self.input = Signal(1 << width)
        self.output = Signal(width)
        self.zero = Signal()
        self.test_zero = test_zero

    def elaborate(self, platform):
        m = Module()

        with OneHotSwitch(m, self.input) as OneHotCase:
            for i in range(len(self.input)):
                with OneHotCase(1 << i):
                    m.d.comb += self.output.eq(i)

            if self.test_zero:
                with OneHotCase():
                    m.d.comb += self.zero.eq(1)

        return m


class TestAssign(TestCaseWithSimulator):
    @parameterized.expand([(False,), (True,)])
    def test_onehotswitch(self, test_zero):
        circuit = OneHotSwitchCircuit(4, test_zero)

        def switch_test_proc():
            for i in range(len(circuit.input)):
                yield circuit.input.eq(1 << i)
                yield Settle()
                assert (yield circuit.output) == i

        with self.run_simulation(circuit) as sim:
            sim.add_process(switch_test_proc)

    def test_onehotswitch_zero(self):
        circuit = OneHotSwitchCircuit(4, True)

        def switch_test_proc_zero():
            for i in range(len(circuit.input)):
                yield circuit.input.eq(1 << i)
                yield Settle()
                assert (yield circuit.output) == i
                assert not (yield circuit.zero)

            yield circuit.input.eq(0)
            yield Settle()
            assert (yield circuit.zero)

        with self.run_simulation(circuit) as sim:
            sim.add_process(switch_test_proc_zero)
