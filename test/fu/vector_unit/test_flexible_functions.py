import random
from collections import deque
from parameterized import parameterized
from amaranth import *
from amaranth.sim import *
from coreblocks.params.isa import *
from coreblocks.fu.vector_unit.flexible_functions import FlexibleAdder, FlexibleElementwiseFunction
from test.common import TestCaseWithSimulator
from test.fu.vector_unit.common import *


class TestFlexibleAdder(TestCaseWithSimulator):
    def setUp(self):
        self.eew = EEW.w64
        self.alu = FlexibleAdder(out_width=self.eew)
        random.seed(15)

        self.elen = eew_to_bits(self.eew)
        max_int = 2 ** (self.elen) - 1
        test_number = 30

        self.test_inputs = deque()
        for i in range(test_number):
            self.test_inputs.append((random.randint(0, max_int), random.randint(0, max_int)))

    def yield_signals(self, substract, in1, in2, op_eew):
        yield self.alu.subtract.eq(substract)
        yield self.alu.in1.eq(in1)
        yield self.alu.in2.eq(in2)
        yield self.alu.eew.eq(op_eew)
        yield Settle()

        # for gtkwave pprint
        yield Delay(10e-7)

        return (yield self.alu.out_data), (yield self.alu.out_carry)

    def check_fn(self, substract, out_fn):
        def process():
            for eew in {EEW.w8, EEW.w16, EEW.w32, EEW.w64}:
                for in1, in2 in self.test_inputs:
                    returned_out, returned_carry = yield from self.yield_signals(
                        substract, C(in1, self.elen), C(in2, self.elen), eew
                    )
                    mask = 2**self.elen - 1
                    correct_out = out_fn(in1 & mask, in2 & mask, eew) & mask
                    self.assertEqual(returned_out, correct_out)

        with self.run_simulation(self.alu) as sim:
            sim.add_process(process)

    def test_add(self):
        self.check_fn(
            False, lambda in1, in2, eew: execute_flexible_operation(lambda x, y: x + y, in1, in2, self.elen, eew)
        )

    def test_substract(self):
        self.check_fn(
            True, lambda in1, in2, eew: execute_flexible_operation(lambda x, y: x - y, in1, in2, self.elen, eew)
        )


class TestFlexibleElementwiseFunction(TestCaseWithSimulator):
    def setUp(self):
        self.test_number = 40
        self.eew = EEW.w32
        self.elen = eew_to_bits(self.eew)
        random.seed(14)

    def yield_signals(self, in1, in2, op_eew):
        yield self.circ.in1.eq(in1)
        yield self.circ.in2.eq(in2)
        yield self.circ.eew.eq(op_eew)
        yield Settle()

        # for gtkwave pprint
        yield Delay(10e-7)

        return (yield self.circ.out_data)

    def gen_process(self, op):
        def process():
            for _ in range(self.test_number):
                for eew in {EEW.w8, EEW.w16, EEW.w32}:
                    in1 = random.randrange(2**self.elen - 1)
                    in2 = random.randrange(2**self.elen - 1)
                    returned_out = yield from self.yield_signals(C(in1, self.elen), C(in2, self.elen), eew)
                    mask = 2**self.elen - 1
                    correct_out = execute_flexible_operation(op, in1 & mask, in2 & mask, self.elen, eew) & mask
                    self.assertEqual(returned_out, correct_out)

        return process

    @parameterized.expand([(lambda x, y: x << ((y % 2**4) if isinstance(y, int) else y[:4]),), (lambda x, y: x + y,)])
    def test_random(self, op):
        self.circ = FlexibleElementwiseFunction(self.eew, op)
        with self.run_simulation(self.circ) as sim:
            sim.add_process(self.gen_process(op))
