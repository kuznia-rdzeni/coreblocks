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

from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import AutoDebugSignals

from test.common import TestCaseWithSimulator, TestbenchIO

from coreblocks.params import GenParams


class UnsignedMultiplicationTestCircuit(Elaboratable, AutoDebugSignals):
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
class UnsignedMultiplicationTestUnit(TestCaseWithSimulator):
    mul_unit: Type[MulBaseUnsigned]
    gen: GenParams

    def setUp(self):
        self.gen = GenParams("rv32im")
        self.m = UnsignedMultiplicationTestCircuit(self.gen, self.mul_unit)

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

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
