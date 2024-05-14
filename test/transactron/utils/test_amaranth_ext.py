from transactron.testing import *
import random
from transactron.utils.amaranth_ext import MultiPriorityEncoder


class TestMultiPriorityEncoder(TestCaseWithSimulator):
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
                    assert (yield valid) == 0
                else:
                    assert (yield valid) == 1
                    assert (yield real) == ex
            yield Delay(1e-7)

    @pytest.mark.parametrize("input_width", [1, 5, 16, 23, 24])
    @pytest.mark.parametrize("output_count", [1, 3, 4])
    def test_random(self, input_width, output_count):
        random.seed(input_width + output_count)
        self.test_number = 50
        self.input_width = input_width
        self.output_count = output_count
        self.circ = MultiPriorityEncoder(self.input_width, self.output_count)

        with self.run_simulation(self.circ) as sim:
            sim.add_process(self.process)

    @pytest.mark.parametrize("name", ["prio_encoder", None])
    def test_static_create_simple(self, name):
        random.seed(14)
        self.test_number = 50
        self.input_width = 7
        self.output_count = 1

        class DUT(Elaboratable):
            def __init__(self, input_width, output_count, name):
                self.input = Signal(input_width)
                self.output_count = output_count
                self.input_width = input_width
                self.name = name

            def elaborate(self, platform):
                m = Module()
                out, val = MultiPriorityEncoder.create_simple(m, self.input_width, self.input, name=self.name)
                # Save as a list to use common interface in testing
                self.outputs = [out]
                self.valids = [val]
                return m

        self.circ = DUT(self.input_width, self.output_count, name)

        with self.run_simulation(self.circ) as sim:
            sim.add_process(self.process)

    @pytest.mark.parametrize("name", ["prio_encoder", None])
    def test_static_create(self, name):
        random.seed(14)
        self.test_number = 50
        self.input_width = 7
        self.output_count = 2

        class DUT(Elaboratable):
            def __init__(self, input_width, output_count, name):
                self.input = Signal(input_width)
                self.output_count = output_count
                self.input_width = input_width
                self.name = name

            def elaborate(self, platform):
                m = Module()
                out = MultiPriorityEncoder.create(m, self.input_width, self.input, self.output_count, name=self.name)
                self.outputs, self.valids = list(zip(*out))
                return m

        self.circ = DUT(self.input_width, self.output_count, name)

        with self.run_simulation(self.circ) as sim:
            sim.add_process(self.process)
