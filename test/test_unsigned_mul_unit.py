import random
from collections import deque
from typing import Type

from amaranth import *
from parameterized import parameterized_class

from coreblocks.mul_params import MulUnitParams
from coreblocks.unsigned_mul_unit import MulBaseUnsigned, ShiftUnsignedMul, SequentialUnsignedMul, RecursiveUnsignedMul
from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.genparams import GenParams


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
    ("name", "gen", "mul_unit"),
    [
        (
            "recursive_multiplicator",
            RecursiveUnsignedMul,
            GenParams("rv32i", mul_unit_params=MulUnitParams.RecursiveMultiplicator(16)),
        ),
        (
            "sequential_multiplication",
            SequentialUnsignedMul,
            GenParams("rv32i", mul_unit_params=MulUnitParams.SequanceMultiplicator(16)),
        ),
        (
            "shift_multiplicator",
            ShiftUnsignedMul,
            GenParams("rv32i", mul_unit_params=MulUnitParams.ShiftMultiplicator()),
        ),
    ],
)
class UnsignedMultiplicationTestUnit(TestCaseWithSimulator):
    gen: GenParams
    mul_unit: Type[MulBaseUnsigned]

    def setUp(self):
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
                print(expected, result)
                self.assertDictEqual(expected, result)
                yield from random_wait()

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield from self.m.issue.call(req)
                print(req)
                yield from random_wait()

        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
