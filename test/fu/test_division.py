import unittest
import random

from amaranth import *
from test.common import *
from coreblocks.utils import align_to_power_of_two, popcount
from parameterized import parameterized_class
from coreblocks.fu.divison.long_division import RecursiveDivison
from coreblocks.params import Funct3, Funct7, OpType, GenParams
from coreblocks.fu.division_unit import DivUnit, DivFn, DivComponent

from test.fu.functional_common import GenericFunctionalTestUnit
from coreblocks.params.configurations import test_core_config

class PopcountTestCircuit(Elaboratable):
    def __init__(self, size: int):
        self.divisor = Signal(size)
        self.dividend = Signal(size)
        self.quotient = Signal(size)
        self.reminder = Signal(size)
        self.size = size    

    def elaborate(self, platform):
        m = Module()

        m.submodules.div = div = RecursiveDivison(self.size, self.size)

        m.d.comb += div.dividend.eq(self.dividend)
        m.d.comb += div.divisor.eq(self.divisor)
        m.d.comb += div.inp.eq(0)
        
        m.d.comb += self.reminder.eq(div.remainder)
        m.d.comb += self.quotient.eq(div.quotient)

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        return m

class TestDiv(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 1
        self.size = 5
        self.m = PopcountTestCircuit(self.size)

    def check(self, d, r):
        yield self.m.dividend.eq(d)
        yield self.m.divisor.eq(r)
        yield Settle()
        reminder = yield self.m.reminder
        quotient = yield self.m.quotient

        print('=========')

        print(f'{d} / {r} = {quotient} rem {reminder}')

        if r != 0:
            self.assertEqual(d // r, quotient, f"")
            self.assertEqual(d % r, reminder, f"")
        else:
            self.assertEqual((1 << self.size) - 1, quotient, f"")
            self.assertEqual(d, reminder, f"")

    def process(self):
        yield from self.check(5, 3)
        yield from self.check(6, 7)
        yield from self.check(1, 1)
        yield from self.check(10, 2)
        yield from self.check(13, 7)
        yield from self.check(12, 5)
        yield from self.check(12, 0)

    def test_popcount(self):
        with self.run_simulation(self.m) as sim:
            sim.add_process(self.process)

def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: DivFn.Fn, xlen: int) -> dict[str, int]:
    signed_i1 = signed_to_int(i1, xlen)
    signed_i2 = signed_to_int(i2, xlen)

    print(f"{i1} {i2} {i1 // i2}")
    if fn == DivFn.Fn.DIV:
        return {"result": (i1 // i2) % (2**xlen)}

    return {"result": 0}


ops = {
    DivFn.Fn.DIV: {"op_type": OpType.DIV_REM, "funct3": Funct3.DIV, "funct7": Funct7.MULDIV},
}

class DivisionUnitTest(GenericFunctionalTestUnit):

    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            DivComponent(),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=1,
            seed=1,
            method_name=method_name,
        )
