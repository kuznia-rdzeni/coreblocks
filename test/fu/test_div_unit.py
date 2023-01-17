import random
from collections import deque
from typing import Type

from amaranth import *
from amaranth.sim import Settle
from parameterized import parameterized_class

from coreblocks.fu.division.common import DividerBase
from coreblocks.fu.division.long import LongDivider

from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import AutoDebugSignals

from test.common import TestCaseWithSimulator, TestbenchIO

from coreblocks.params import GenParams
from test.fu.functional_common import FunctionalTestCircuit


class UnsignedMultiplicationTestCircuit(Elaboratable, AutoDebugSignals):
    def __init__(self, gen: GenParams, div_unit: Type[DividerBase]):
        self.gen = gen
        self.div_unit = div_unit

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.func_unit = func_unit = self.div_unit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return tm


@parameterized_class(
    ("name", "div_unit", "gen"),
    [
        (
            "long_divider",
            LongDivider,
            GenParams("rv32im"),
        ),
    ],
)
class DivisionTestUnit(TestCaseWithSimulator):
    div_unit: Type[DividerBase]
    gen: GenParams

    def setUp(self):
        self.m = FunctionalTestCircuit(self.gen, self.div_unit)

        random.seed(1050)
        self.requests = deque()
        self.responses = deque()
        max_int = 2**self.gen.isa.xlen - 1
        for _ in range(100):
            data1 = random.randint(1, max_int)
            data2 = random.randint(1, max_int)
            q = data1 // data2
            r = data1 % data2

            self.requests.append(
                {
                    "dividend": data1,
                    "divisor": data2,
                }
            )
            self.responses.append({"q": q, "r": r})

    def test_pipeline(self):
        def random_wait():
            for _ in range(random.randint(0, 10)):
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
