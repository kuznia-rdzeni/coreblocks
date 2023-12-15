import random
from collections import deque
from typing import Type

from amaranth import *
from amaranth.sim import Settle
from parameterized import parameterized_class

from coreblocks.fu.unsigned_multiplication.common import MulBaseUnsigned
from coreblocks.fu.unsigned_multiplication.fast_recursive import RecursiveUnsignedMul
from coreblocks.fu.unsigned_multiplication.sequence import SequentialUnsignedMul
from coreblocks.fu.unsigned_multiplication.shift import ShiftUnsignedMul

from transactron import *
from transactron.lib import *

from test.common import CoreblocksTestCaseWithSimulator, TestbenchIO

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config


class UnsignedMultiplicationTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, mul_unit: Type[MulBaseUnsigned]):
        self.gen_params = gen_params
        self.mul_unit = mul_unit

    def elaborate(self, platform):
        m = Module()

        m.submodules.func_unit = func_unit = self.mul_unit(self.gen_params)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return m


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
    ],
)
class UnsignedMultiplicationTestUnit(CoreblocksTestCaseWithSimulator):
    mul_unit: Type[MulBaseUnsigned]

    def setUp(self):
        self.gen_params = GenParams(test_core_config)
        self.m = UnsignedMultiplicationTestCircuit(self.gen_params, self.mul_unit)

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
        def random_wait():
            for i in range(random.randint(0, 10)):
                yield

        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                self.assertDictEqual(expected, result)
                yield from random_wait()

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield Settle()
                yield from self.m.issue.call(req)
                yield from random_wait()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
