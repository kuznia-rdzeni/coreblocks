import random
from collections import deque
import operator

from amaranth import *
from amaranth.sim import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from ..common import TestCaseWithSimulator, TestbenchIO, test_gen_params

from coreblocks.fu.alu import AluFn, Alu, AluFuncUnit
from coreblocks.params import *


def _cast_to_int_xlen(x, xlen):
    if xlen == 32:
        return -int(0x100000000 - x) if (x > 0x7FFFFFFF) else x
    elif xlen == 64:
        return -int(0x10000000000000000 - x) if (x > 0x7FFFFFFFFFFFFFFF) else x
    return 0


class TestAlu(TestCaseWithSimulator):
    TEST_INPUTS = [
        (312123, 4),
        (115478972, 312351066),
        (55, 10),
        (0, 0),
        (4294967295, 1),
        (0, 4294967295),
        (4294967295, 1),
        (4294967295, 4294967295),
        (4294967293, 2),
        (2, 0),
    ]

    def setUp(self):
        self.gen = test_gen_params("rv32i")
        self.alu = Alu(self.gen)

        random.seed(42)

        # Supply hand-written tests with random test inputs
        self.test_inputs = TestAlu.TEST_INPUTS
        max_int = 2**self.gen.isa.xlen - 1
        for i in range(20):
            self.test_inputs.append((random.randint(0, max_int), random.randint(0, max_int)))

    def yield_signals(self, fn, in1, in2):
        yield self.alu.fn.eq(fn)
        yield self.alu.in1.eq(in1)
        yield self.alu.in2.eq(in2)
        yield Settle()

        return (yield self.alu.out)

    def check_fn(self, fn, out_fn):
        def process():
            for (in1, in2) in self.test_inputs:
                returned_out = yield from self.yield_signals(fn, C(in1, self.gen.isa.xlen), C(in2, self.gen.isa.xlen))
                mask = 2**self.gen.isa.xlen - 1
                correct_out = out_fn(in1 & mask, in2 & mask) & mask
                self.assertEqual(returned_out, correct_out)

        with self.run_simulation(self.alu) as sim:
            sim.add_process(process)

    def test_add(self):
        self.check_fn(AluFn.Fn.ADD, operator.add)

    def test_sll(self):
        self.check_fn(AluFn.Fn.SLL, lambda in1, in2: in1 << (in2 & (self.gen.isa.xlen - 1)))

    def test_xor(self):
        self.check_fn(AluFn.Fn.XOR, operator.xor)

    def test_srl(self):
        self.check_fn(AluFn.Fn.SRL, lambda in1, in2: in1 >> (in2 & (self.gen.isa.xlen - 1)))

    def test_or(self):
        self.check_fn(AluFn.Fn.OR, operator.or_)

    def test_and(self):
        self.check_fn(AluFn.Fn.AND, operator.and_)

    def test_sub(self):
        self.check_fn(AluFn.Fn.SUB, operator.sub)

    def test_sra(self):
        def sra(in1, in2):
            xlen = self.gen.isa.xlen
            in2 = in2 & (xlen - 1)
            if in1 & 2 ** (xlen - 1) != 0:
                return (((2**xlen) - 1) << xlen | in1) >> in2
            else:
                return in1 >> in2

        self.check_fn(AluFn.Fn.SRA, sra)

    def test_slt(self):
        self.check_fn(
            AluFn.Fn.SLT,
            lambda in1, in2: _cast_to_int_xlen(in1, self.gen.isa.xlen) < _cast_to_int_xlen(in2, self.gen.isa.xlen),
        )

    def test_sltu(self):
        self.check_fn(AluFn.Fn.SLTU, operator.lt)


class AluFuncUnitTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.func_unit = func_unit = AluFuncUnit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return tm


class TestAluFuncUnit(TestCaseWithSimulator):
    def setUp(self):
        self.gen = test_gen_params("rv32i")
        self.m = AluFuncUnitTestCircuit(self.gen)

        random.seed(42)
        self.requests = deque()
        self.responses = deque()
        max_int = 2**self.gen.isa.xlen - 1
        for i in range(50):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            rob_id = random.randint(0, 2**self.gen.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2**self.gen.phys_regs_bits - 1)
            exec_fn = {"op_type": OpType.ARITHMETIC, "funct3": Funct3.ADD, "funct7": Funct7.ADD}
            result = (data1 + data2) & max_int

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

    def test_randomized(self):
        def random_wait():
            for i in range(random.randint(0, 5)):
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
                yield from self.m.issue.call(req)
                yield from random_wait()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)

    def test_pipeline(self):
        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                self.assertDictEqual(expected, result)

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield from self.m.issue.call_init(req)
                yield
                self.assertTrue((yield from self.m.issue.done()))

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
