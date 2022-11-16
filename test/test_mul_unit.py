import random
from collections import deque

from amaranth import *

from coreblocks.isa import OpType, Funct3, Funct7
from coreblocks.mul_unit import MulUnit, MulFn
from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from .common import TestCaseWithSimulator, TestbenchIO, signed_to_int, int_to_signed

from coreblocks.genparams import GenParams


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


def compute_result(i1: int, i2: int, fn: MulFn.Fn, xlen: int) -> int:
    signed_i1 = signed_to_int(i1, xlen)
    signed_i2 = signed_to_int(i2, xlen)
    if fn == MulFn.Fn.MUL:
        return (i1 * i2) % (2**xlen)
    elif fn == MulFn.Fn.MULH:
        return int_to_signed(signed_i1 * signed_i2, 2 * xlen) // (2**xlen)
    elif fn == MulFn.Fn.MULHU:
        return i1 * i2 // (2**xlen)
    elif fn == MulFn.Fn.MULHSU:
        return int_to_signed(signed_i1 * i2, 2 * xlen) // (2**xlen)
    else:
        signed_half_i1 = signed_to_int(i1 % (2 ** (xlen // 2)), xlen // 2)
        signed_half_i2 = signed_to_int(i2 % (2 ** (xlen // 2)), xlen // 2)
        return int_to_signed(signed_half_i1 * signed_half_i2, xlen)


class FullMultiplicationTestUnit(TestCaseWithSimulator):
    def setUp(self):
        self.gen = GenParams("rv32i")
        self.m = FullMultiplicationTestCircuit(self.gen)

        random.seed(40)
        self.requests = deque()
        self.responses = deque()

        max_int = 2**self.gen.isa.xlen - 1
        mul_fns = [MulFn.Fn.MUL, MulFn.Fn.MULH, MulFn.Fn.MULHU, MulFn.Fn.MULHSU, MulFn.Fn.MULW]
        ops = {
            MulFn.Fn.MUL: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MUL, "funct7": Funct7.MULDIV},
            MulFn.Fn.MULH: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MULH, "funct7": Funct7.MULDIV},
            MulFn.Fn.MULHU: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MULHU, "funct7": Funct7.MULDIV},
            MulFn.Fn.MULHSU: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MULHSU, "funct7": Funct7.MULDIV},
            MulFn.Fn.MULW: {"op_type": OpType.ARITHMETIC_W, "funct3": Funct3.MULW, "funct7": Funct7.MULDIV},
        }

        for i in range(2000):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            mul_fn = mul_fns[random.randint(0, len(mul_fns) - 1)]
            rob_id = random.randint(0, 2**self.gen.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2**self.gen.phys_regs_bits - 1)
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
