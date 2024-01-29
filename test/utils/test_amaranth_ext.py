from test.common import *
import random
from transactron.utils.amaranth_ext import MultiPriorityEncoder


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
            yield Delay(1e-7)

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            sim.add_process(self.process)
