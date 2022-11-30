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
from coreblocks.params.mul_params import MulUnitParams

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from test.common import TestCaseWithSimulator, TestbenchIO

from coreblocks.params import GenParams
from test.fu.functional_common import FunctionalTestCircuit


class UnsignedMultiplicationTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams, mul_unit: Type[MulBaseUnsigned]):
        self.gen = gen
        self.mul_unit = mul_unit

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.func_unit = func_unit = self.mul_unit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return tm


@parameterized_class(
    ("name", "mul_unit", "gen"),
    [
        (
            "recursive_multiplicator",
            RecursiveUnsignedMul,
            GenParams("rv32i", mul_unit_params=MulUnitParams.RecursiveMultiplier(16)),
        ),
        (
            "sequential_multiplication",
            SequentialUnsignedMul,
            GenParams("rv32i", mul_unit_params=MulUnitParams.SequenceMultiplier(16)),
        ),
        (
            "shift_multiplicator",
            ShiftUnsignedMul,
            GenParams("rv32i", mul_unit_params=MulUnitParams.ShiftMultiplier()),
        ),
    ],
)
class UnsignedMultiplicationTestUnit(TestCaseWithSimulator):
    mul_unit: Type[MulBaseUnsigned]
    gen: GenParams

    def setUp(self):
        self.m = FunctionalTestCircuit(self.gen, self.mul_unit)

        random.seed(1050)
        self.requests = deque()
        self.responses = deque()
        max_int = 2**self.gen.isa.xlen - 1
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

        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
