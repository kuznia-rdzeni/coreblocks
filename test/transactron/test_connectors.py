import random
from parameterized import parameterized_class

from amaranth.sim import Settle, Tick

from transactron.lib import StableSelectingNetwork
from transactron.testing import TestCaseWithSimulator


@parameterized_class(
    ("n"),
    [(2,), (3,), (7,), (8,)],
)
class TestStableSelectingNetwork(TestCaseWithSimulator):
    n: int

    def test(self):
        m = StableSelectingNetwork(self.n, [("data", 8)])

        random.seed(42)

        def process():
            for _ in range(100):
                inputs = [random.randrange(2**8) for _ in range(self.n)]
                valids = [random.randrange(2) for _ in range(self.n)]
                total = sum(valids)

                expected_output_prefix = []
                for i in range(self.n):
                    yield m.valids[i].eq(valids[i])
                    yield m.inputs[i].data.eq(inputs[i])

                    if valids[i]:
                        expected_output_prefix.append(inputs[i])

                yield Settle()

                for i in range(total):
                    out = yield m.outputs[i].data
                    assert out == expected_output_prefix[i]

                assert (yield m.output_cnt) == total
                yield Tick()

        with self.run_simulation(m) as sim:
            sim.add_process(process)
