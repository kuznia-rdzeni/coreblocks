from coreblocks.params import Funct3, Funct7, GenParams, OpType
from coreblocks.params.configurations import test_core_config
from coreblocks.fu.alu import AluFn, ALUComponent, AluFuncUnit

from test.fu.functional_common import FunctionalUnitTestCase

import random
from collections import deque

from amaranth import *
from amaranth.sim import *

from coreblocks.transactions import *
from coreblocks.transactions.lib import *

from ..common import RecordIntDict, TestCaseWithSimulator, TestbenchIO
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
        case AluFn.Fn.ANDN:
            res = i1 & ~val2
        case AluFn.Fn.XNOR:
            res = ~(i1 ^ val2)
        case AluFn.Fn.ORN:
            res = i1 | ~val2
        case AluFn.Fn.MAX:
            res = max(signed_to_int(i1, xlen), signed_to_int(val2, xlen))
        case AluFn.Fn.MAXU:
            res = max(i1, val2)
        case AluFn.Fn.MIN:
            res = min(signed_to_int(i1, xlen), signed_to_int(val2, xlen))
        case AluFn.Fn.MINU:
            res = min(i1, val2)
        case AluFn.Fn.CPOP:
            res = i1.bit_count()
        case AluFn.Fn.SEXTH:
            bit = (i1 >> 15) & 1
            if bit:
                res = i1 | (mask ^ 0xFFFF)
            else:
                res = i1 & 0xFFFF
        case AluFn.Fn.SEXTB:
            bit = (i1 >> 7) & 1
            if bit:
                res = i1 | (mask ^ 0xFF)
            else:
                res = i1 & 0xFF
        case AluFn.Fn.ZEXTH:
            res = i1 & 0xFFFF
        case AluFn.Fn.ORCB:
            i1 |= i1 >> 1
            i1 |= i1 >> 2
            i1 |= i1 >> 4

            i1 &= 0x010101010101010101

            for i in range(8):
                res |= i1 << i
        case AluFn.Fn.REV8:
            for i in range(xlen // 8):
                res = (res << 8) | (i1 & 0xFF)
                i1 >>= 8  # Haskell screams in pain
        case AluFn.Fn.CLZ:
            res = xlen - i1.bit_length()
        case AluFn.Fn.CTZ:
            if i1 == 0:
                res = xlen.bit_length()
            else:
                while (i1 & 1) == 0:
                    res += 1
                    i1 >>= 1

    return {"result": res & mask}


ops: dict[AluFn.Fn, RecordIntDict] = {
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
    AluFn.Fn.ANDN: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.ANDN,
        "funct7": Funct7.ANDN,
    },
    AluFn.Fn.XNOR: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.XNOR,
        "funct7": Funct7.XNOR,
    },
    AluFn.Fn.ORN: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.ORN,
        "funct7": Funct7.ORN,
    },
    AluFn.Fn.MAX: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.MAX,
        "funct7": Funct7.MAX,
    },
    AluFn.Fn.MAXU: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.MAXU,
        "funct7": Funct7.MAX,
    },
    AluFn.Fn.MIN: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.MIN,
        "funct7": Funct7.MIN,
    },
    AluFn.Fn.MINU: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.MINU,
        "funct7": Funct7.MIN,
    },
    AluFn.Fn.CPOP: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_5,
        "funct3": Funct3.CPOP,
        "funct7": Funct7.CPOP,
    },
    AluFn.Fn.SEXTB: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_1,
        "funct3": Funct3.SEXTB,
        "funct7": Funct7.SEXTB,
    },
    AluFn.Fn.ZEXTH: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_1,
        "funct3": Funct3.ZEXTH,
        "funct7": Funct7.ZEXTH,
    },
    AluFn.Fn.SEXTH: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_2,
        "funct3": Funct3.SEXTH,
        "funct7": Funct7.SEXTH,
    },
    AluFn.Fn.ORCB: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_1,
        "funct3": Funct3.ORCB,
        "funct7": Funct7.ORCB,
    },
    AluFn.Fn.REV8: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_1,
        "funct3": Funct3.REV8,
        "funct7": Funct7.REV8,
    },
    AluFn.Fn.CLZ: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_3,
        "funct3": Funct3.CLZ,
        "funct7": Funct7.CLZ,
    },
    AluFn.Fn.CTZ: {
        "op_type": OpType.UNARY_BIT_MANIPULATION_4,
        "funct3": Funct3.CTZ,
        "funct7": Funct7.CTZ,
    },
}


class AluUnitTest(FunctionalUnitTestCase[AluFn.Fn]):
    def test_test(self):
        self.run_fu_test()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ALUComponent(zba_enable=True, zbb_enable=True),
            compute_result,
            gen=GenParams(test_core_config),
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
            self.responses.append({"rob_id": rob_id, "result": result, "rp_dst": rp_dst, "exception": 0})

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
