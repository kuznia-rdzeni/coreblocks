import random
from collections import deque

from parameterized import parameterized_class

from coreblocks.func_blocks.fu.unsigned_multiplication.common import MulBaseUnsigned
from coreblocks.func_blocks.fu.unsigned_multiplication.fast_recursive import RecursiveUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.sequence import SequentialUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.shift import ShiftUnsignedMul
from coreblocks.func_blocks.fu.unsigned_multiplication.pipelined import PipelinedUnsignedMul

from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.testing.functions import data_const_to_dict


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
            "pipelined_multiplier",
            PipelinedUnsignedMul,
        ),
    ],
)
class TestUnsignedMultiplicationUnit(TestCaseWithSimulator):
    mul_unit: type[MulBaseUnsigned]

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
        async def consumer(sim: TestbenchContext):
            while self.responses:
                expected = self.responses.pop()
                result = await self.m.accept.call(sim)
                assert expected == data_const_to_dict(result)
                await self.random_wait(sim, self.waiting_time)

        async def producer(sim: TestbenchContext):
            while self.requests:
                req = self.requests.pop()
                await self.m.issue.call(sim, req)
                await self.random_wait(sim, self.waiting_time)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)
