import random
from collections import deque

from amaranth import *
from amaranth.sim import *

from ...common import TestCaseWithSimulator

from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.flexible_alu import FlexibleAdder


def split_flex(n: int, elen: int, eew: EEW):
    ebits = eew_to_bits(eew)
    while elen > 0:
        yield n % (2**ebits)
        n = n >> ebits
        elen -= ebits


def glue_flex(elems: list[int], elen: int, eew: EEW) -> int:
    out = 0
    ebits = eew_to_bits(eew)
    mask = 2**ebits - 1
    print(elems)
    for elem in reversed(elems):
        out = (out << ebits) | (elem & mask)
    return out


def op_flex(substract: bool, in1: int, in2: int, elen: int, eew: EEW) -> int:
    out_elems = []
    for elem1, elem2 in zip(split_flex(in1, elen, eew), split_flex(in2, elen, eew)):
        if substract:
            out_elems.append(elem1 - elem2)
        else:
            out_elems.append(elem1 + elem2)
    return glue_flex(out_elems, elen, eew)


class TestFlexibleAdder(TestCaseWithSimulator):
    def setUp(self):
        self.eew = EEW.w16
        self.alu = FlexibleAdder(out_width=self.eew)
        random.seed(14)

        self.elen = eew_to_bits(self.eew)
        max_int = 2 ** (self.elen) - 1
        test_number = 2

        self.test_inputs = deque()
        for i in range(test_number):
            self.test_inputs.append((random.randint(0, max_int), random.randint(0, max_int)))

    def yield_signals(self, substract, in1, in2, op_eew):
        yield self.alu.substract.eq(substract)
        yield self.alu.in1.eq(in1)
        yield self.alu.in2.eq(in2)
        yield Settle()

        return (yield self.alu.out_data)

    def check_fn(self, substract, out_fn):
        def process():
            for eew in {EEW.w8, EEW.w16}:#, EEW.w32, EEW.w64}:
                for in1, in2 in self.test_inputs:
                    print("Nowy test")
                    returned_out = yield from self.yield_signals(substract, C(in1, self.elen), C(in2, self.elen), eew)
                    mask = 2**self.elen - 1
                    correct_out = out_fn(in1 & mask, in2 & mask, eew) & mask
                    self.assertEqual(returned_out, correct_out)

        with self.run_simulation(self.alu) as sim:
            sim.add_process(process)

    def test_add(self):
        self.check_fn(False, lambda in1, in2, eew: op_flex(False, in1, in2, self.elen, eew))

    def test_substract(self):
        self.check_fn(True, lambda in1, in2, eew: op_flex(False, in1, in2, self.elen, eew))
