from amaranth import *
from amaranth.sim import *

from coreblocks.utils import rotate_left, rotate_right

from test.common import TestCaseWithSimulator


class CircularShiftCircuit(Elaboratable):
    def __init__(self, width: int):
        self.width = width

        self.input = Signal(width)

        # Output for each possible shift
        self.outputs_rol = [Signal(width) for _ in range(width)]
        self.outputs_ror = [Signal(width) for _ in range(width)]

    def elaborate(self, platform):
        m = Module()

        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)

        for i in range(self.width):
            m.d.comb += self.outputs_rol[i].eq(rotate_left(self.input, shift=i))
            m.d.comb += self.outputs_ror[i].eq(rotate_right(self.input, shift=i))

        return m


class TestCircularShifts(TestCaseWithSimulator):
    def test_shifts(self):
        m = CircularShiftCircuit(width=8)

        test_cases = [
            (0b00010011, 2, 0b01001100, 0b11000100),
            (0b00110000, 1, 0b01100000, 0b00011000),
            (0b11010000, 3, 0b10000110, 0b00011010),
            (0b00010000, 2, 0b01000000, 0b00000100),
            (0b11111110, 5, 0b11011111, 0b11110111),
            (0b00000111, 0, 0b00000111, 0b00000111),
            (0b00000111, 7, 0b10000011, 0b00001110),
        ]

        def proc():
            for input, shift, expected_rol, expected_ror in test_cases:
                yield m.input.eq(input)
                yield
                self.assertEqual((yield m.outputs_rol[shift]), expected_rol)
                self.assertEqual((yield m.outputs_ror[shift]), expected_ror)
                yield

        with self.run_simulation(m) as sim:
            sim.add_sync_process(proc)
