import random
import math
from collections import deque

from parameterized import parameterized_class

from coreblocks.func_blocks.fu.unsigned_multiplication.pipelined import PipelinedUnsignedMul

from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.testing.functions import data_const_to_dict


@parameterized_class(
    ("dsp_width", "dsp_number"),
    [
        (18, 4),
        (8, 4),
        (18, 2),
        (4, 4),
    ],
)
class TestPipelinedUnsignedMul(TestCaseWithSimulator):
    dsp_width: int
    dsp_number: int

    def setup_method(self):
        self.gen_params = GenParams(test_core_config)
        self.m = SimpleTestCircuit(PipelinedUnsignedMul(self.gen_params, self.dsp_width, self.dsp_number))
        self.n_padding = self.dsp_width * 2 ** (math.ceil(math.log2(self.gen_params.isa.xlen / self.dsp_width)))
        self.number_of_chunks = self.n_padding // self.dsp_width
        self.number_of_multiplications = self.number_of_chunks**2
        self.pipeline_length = math.ceil(math.log2(self.number_of_chunks))
        self.number_of_factors = 100

        random.seed(1050)
        self.requests = deque()
        self.responses = deque()
        max_int = 2**self.gen_params.isa.xlen - 1
        for i in range(self.number_of_factors):
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
            time = 0
            while self.responses:
                res = await self.m.accept.call_try(sim)
                time += 1
                if res is not None:
                    expected = self.responses.pop()
                    assert expected == data_const_to_dict(res)

            assert (
                time
                == self.number_of_factors * math.ceil(self.number_of_multiplications / self.dsp_number)
                + self.pipeline_length
                + 2
            )

        async def producer(sim: TestbenchContext):
            while self.requests:
                req = self.requests.pop()
                await self.m.issue.call(sim, req)

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)
