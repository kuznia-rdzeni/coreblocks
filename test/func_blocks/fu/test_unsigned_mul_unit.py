import random
from collections import deque
from typing import Type

from amaranth.sim import Settle
from parameterized import parameterized_class

from coreblocks.func_blocks.fu.unsigned_multiplication.common import MulBaseUnsigned
from coreblocks.func_blocks.fu.unsigned_multiplication.fast_recursive import RecursiveUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.sequence import SequentialUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.shift import ShiftUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.iterative_multiplication import IterativeUnsignedMul

from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config


@parameterized_class(
    ("name", "mul_unit"),
    [
        (
            "recursive_multiplier",
            RecursiveUnsignedMul,
        ),
        (
            "sequential_multiplier",
            SequentialUnsignedMul,
        ),
        (
            "shift_multiplier",
            ShiftUnsignedMul,
        ),
        (
            "iterative_multiplier",
            IterativeUnsignedMul,
        ),
    ],
)
class TestUnsignedMultiplicationUnit(TestCaseWithSimulator):
    mul_unit: Type[MulBaseUnsigned]

    def setup_method(self):
        self.gen_params = GenParams(test_core_config)
        self.m = SimpleTestCircuit(self.mul_unit(self.gen_params))
        self.waiting_time = 10

        random.seed(1050)
        self.requests = deque()
        self.responses = deque()
        max_int = 2**self.gen_params.isa.xlen - 1
        for i in range(100):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            result = data1 * data2

            self.requests.append(
                {
                    "i1": data1,
                    "i2": data2,
                }
            )
            self.responses.append(
                {
                    "o": result,
                }
            )

    def test_pipeline(self):
        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                assert expected == result
                yield from self.random_wait(self.waiting_time)

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield Settle()
                yield from self.m.issue.call(req)
                yield from self.random_wait(self.waiting_time)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
