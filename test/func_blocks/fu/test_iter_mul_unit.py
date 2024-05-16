import random
from collections import deque

from amaranth.sim import Settle
from parameterized import parameterized_class

from coreblocks.func_blocks.fu.unsigned_multiplication.iterative_multiplication import IterativeUnsignedMul

from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config


@parameterized_class(
    ("dsp_width", "dsp_number"),
    [
        (18, 4),
        (8, 4),
        (18, 2),
        (4, 4),
    ],
)
class TestUnsignedMultiplicationUnit(TestCaseWithSimulator):
    dsp_width: int
    dsp_number: int

    def setup_method(self):
        self.gen_params = GenParams(test_core_config)
        self.m = SimpleTestCircuit(IterativeUnsignedMul(self.gen_params, self.dsp_width, self.dsp_number))
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
            waiting = 0
            while self.responses:
                res = yield from self.m.accept.call_try()
                if res is None:
                    busy = 1
                else:
                    busy = 0
                waiting = waiting + busy
                if busy == 0:
                    expected = self.responses.pop()
                    assert expected == res
                yield
            with open("iterative_multiplication_busy.txt", "a") as file:
                file.write(f"dsp_width:{self.m._dut.dsp_width},dsp_number:{self.m._dut.dsp_number} -> {waiting}\n")

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield Settle()
                yield from self.m.issue.call(req)

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
