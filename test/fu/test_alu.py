from coreblocks.params import Funct3, Funct7, GenParams, OpType
from coreblocks.params.configurations import test_core_config
from coreblocks.fu.alu import AluFn, ALUComponent, AluFuncUnit

from test.fu.functional_common import GenericFunctionalTestUnit

import random
from collections import deque

from amaranth import *
from amaranth.sim import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from ..common import TestCaseWithSimulator, TestbenchIO
from test.common import signed_to_int


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: AluFn.Fn, xlen: int) -> dict[str, int]:
    val2 = i_imm if i_imm else i2
    mask = (1 << xlen) - 1

    res = 0

    match fn:
        case AluFn.Fn.ADD:
            res = i1 + val2
        case AluFn.Fn.SUB:
            res = i1 - val2
        case AluFn.Fn.XOR:
            res = i1 ^ val2
        case AluFn.Fn.OR:
            res = i1 | val2
        case AluFn.Fn.AND:
            res = i1 & val2
        case AluFn.Fn.SLT:
            res = signed_to_int(i1, xlen) < signed_to_int(val2, xlen)
        case AluFn.Fn.SLTU:
            res = i1 < val2
        case AluFn.Fn.SH1ADD:
            res = (i1 << 1) + val2
        case AluFn.Fn.SH2ADD:
            res = (i1 << 2) + val2
        case AluFn.Fn.SH3ADD:
            res = (i1 << 3) + val2

    return {"result": res & mask}


ops = {
    AluFn.Fn.ADD: {
        "op_type": OpType.ARITHMETIC,
        "funct3": Funct3.ADD,
        "funct7": Funct7.ADD,
    },
    AluFn.Fn.SUB: {
        "op_type": OpType.ARITHMETIC,
        "funct3": Funct3.ADD,
        "funct7": Funct7.SUB,
    },
    AluFn.Fn.SLT: {
        "op_type": OpType.COMPARE,
        "funct3": Funct3.SLT,
    },
    AluFn.Fn.SLTU: {
        "op_type": OpType.COMPARE,
        "funct3": Funct3.SLTU,
    },
    AluFn.Fn.XOR: {
        "op_type": OpType.LOGIC,
        "funct3": Funct3.XOR,
    },
    AluFn.Fn.OR: {
        "op_type": OpType.LOGIC,
        "funct3": Funct3.OR,
    },
    AluFn.Fn.AND: {
        "op_type": OpType.LOGIC,
        "funct3": Funct3.AND,
    },
    AluFn.Fn.SH1ADD: {
        "op_type": OpType.ADDRESS_GENERATION,
        "funct3": Funct3.SH1ADD,
        "funct7": Funct7.SH1ADD,
    },
    AluFn.Fn.SH2ADD: {
        "op_type": OpType.ADDRESS_GENERATION,
        "funct3": Funct3.SH2ADD,
        "funct7": Funct7.SH2ADD,
    },
    AluFn.Fn.SH3ADD: {
        "op_type": OpType.ADDRESS_GENERATION,
        "funct3": Funct3.SH3ADD,
        "funct7": Funct7.SH3ADD,
    },
}


class AluUnitTest(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ALUComponent(zba_enable=True),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=800,
            seed=42,
            method_name=method_name,
            zero_imm=False,
        )


class AluFuncUnitTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams):
        self.gen = gen

    def elaborate(self, platform):
        m = Module()

        m.submodules.func_unit = func_unit = AluFuncUnit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return m


class TestAluFuncUnit(TestCaseWithSimulator):
    def setUp(self):
        self.gen = GenParams(test_core_config)
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
