import random
from collections import deque
from typing import Type

from amaranth import *

from coreblocks.isa import OpType, Funct3, Funct7
from coreblocks.mul_unit import MulBaseUnsigned, ShiftUnsignedMul, MulUnit, MulFn
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

        # m.submodules.func_unit = func_unit = ShiftUnsignedMul(self.gen)
        m.submodules.func_unit = func_unit = self.mul_unit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return tm


class FullMultiplicationTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        # m.submodules.func_unit = func_unit = ShiftUnsignedMul(self.gen)
        m.submodules.func_unit = func_unit = MulUnit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return tm


def neg(x: int, xlen: int) -> int:
    base = 2 ** xlen - 1
    return ((x ^ base) + 1) & base


def int_to_signed(x: int, xlen: int) -> int:
    if x < 0:
        return neg(-x, xlen)
    else:
        return x

def signed_to_int(x: int, xlen: int) -> int:
    sign = 2 ** (xlen - 1)
    if (sign & x) == sign:
        return -(x ^ sign)
    else:
        return x

def compute_result(i1: int, i2: int, fn : MulFn.Fn, xlen: int) -> int:
    signed_i1 = signed_to_int(i1, xlen)
    signed_i2 = signed_to_int(i2, xlen)
    if fn == MulFn.Fn.MUL:
        return (i1 * i2) % (2 ** xlen)
    elif fn == MulFn.Fn.MULH:
        return int_to_signed((signed_i1 * signed_i2) // (2 ** xlen), xlen)
    elif fn == MulFn.Fn.MULHU:
        return i1 * i2 // (2 ** xlen)
    elif fn == MulFn.Fn.MULHSU:
        return int_to_signed((i1 * signed_i2) // (2 ** xlen), xlen)
    else:
        signed_half_i1 = signed_to_int(i1 % (2 ** (xlen // 2)), xlen // 2)
        signed_half_i2 = signed_to_int(i1 % (2 ** (xlen // 2)), xlen // 2)
        return int_to_signed(signed_half_i1 * signed_half_i2, xlen)


class FullMultiplicationTestUnit(TestCaseWithSimulator):
    def setUp(self):
        self.gen = GenParams("rv32i")
        self.m = FullMultiplicationTestCircuit(self.gen)

        random.seed(40)
        self.requests = deque()
        self.responses = deque()

        max_int = 2 ** self.gen.isa.xlen - 1
        mul_fns = [MulFn.Fn.MUL, MulFn.Fn.MULH, MulFn.Fn.MULHU, MulFn.Fn.MULHSU]
        ops = {
            MulFn.Fn.MUL:    {"op_type": OpType.ARITHMETIC,   "funct3": Funct3.MUL,    "funct7": Funct7.MULDIV},
            MulFn.Fn.MULH:   {"op_type": OpType.ARITHMETIC,   "funct3": Funct3.MULH,   "funct7": Funct7.MULDIV},
            MulFn.Fn.MULHU:  {"op_type": OpType.ARITHMETIC,   "funct3": Funct3.MULHU,  "funct7": Funct7.MULDIV},
            MulFn.Fn.MULHSU: {"op_type": OpType.ARITHMETIC,   "funct3": Funct3.MULHSU, "funct7": Funct7.MULDIV},
            MulFn.Fn.MULW:   {"op_type": OpType.ARITHMETIC_W, "funct3": Funct3.MULW,   "funct7": Funct7.MULDIV},
        }

        for i in range(1000):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            mul_fn = mul_fns[random.randint(0, len(mul_fns) - 1)]
            rob_id = random.randint(0, 2 ** self.gen.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2 ** self.gen.phys_regs_bits - 1)
            exec_fn = ops[mul_fn]
            result = compute_result(data1, data2, mul_fn, self.gen.isa.xlen)

            self.requests.append(
                {
                    "s1_val": data1,
                    "s2_val": 0 if data2_is_imm else data2,
                    "rob_id": rob_id,
                    "exec_fn": exec_fn,
                    "rp_dst": rp_dst,
                    "imm": data2 if data2_is_imm else 0,
                }
            )
            self.responses.append({"rob_id": rob_id, "result": result, "rp_dst": rp_dst})

    def test_pipeline(self):
        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                print(result)
                self.assertDictEqual(expected, result)

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield from self.m.issue.call(req)
                print(req)

        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)


class AbstractUnsignedMultiplicationTestUnit(TestCaseWithSimulator):
    def __init__(self, mul_unit: Type[MulBaseUnsigned], method_name='runTest'):
        super().__init__(method_name)
        self.mul_unit = mul_unit

    def setUp(self):
        self.gen = GenParams("rv32i")
        self.m = UnsignedMultiplicationTestCircuit(self.gen, self.mul_unit)

        random.seed(1050)
        self.requests = deque()
        self.responses = deque()
        max_int = 2 ** self.gen.isa.xlen - 1
        for i in range(100):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            result = data1 * data2

            self.requests.append({
                "i1": data1,
                "i2": data2,
            })
            self.responses.append({
                "o": result,
            })

    def abstract_test_pipeline(self):
        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                print(result)
                self.assertDictEqual(expected, result)

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield from self.m.issue.call(req)
                print(req)

        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)


class FastRecursiveMultiplicationTest(AbstractUnsignedMultiplicationTestUnit):
    def __init__(self, method_name='runTest'):
        super().__init__(MulBaseUnsigned, method_name)

    def test_pipeline(self):
        self.abstract_test_pipeline()


class ShiftMultiplicationTest(AbstractUnsignedMultiplicationTestUnit):
    def __init__(self, method_name='runTest'):
        super().__init__(ShiftUnsignedMul, method_name)

    def test_pipeline(self):
        self.abstract_test_pipeline()
