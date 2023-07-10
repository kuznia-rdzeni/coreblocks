from coreblocks.params import Funct3, Funct7, OpType, GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.fu.shift_unit import ShiftUnitFn, ShiftUnitComponent
from test.common import RecordIntDict

from test.fu.functional_common import FunctionalUnitTestCase


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ShiftUnitFn.Fn, xlen: int) -> dict[str, int]:
    val2 = i_imm if i_imm else i2

    mask = (1 << xlen) - 1
    res = 0
    shamt = val2 & (xlen - 1)

    match fn:
        case ShiftUnitFn.Fn.SLL:
            res = i1 << shamt
        case ShiftUnitFn.Fn.SRA:
            if i1 & 2 ** (xlen - 1) != 0:
                res = (((1 << xlen) - 1) << xlen | i1) >> shamt
            else:
                res = i1 >> shamt
        case ShiftUnitFn.Fn.SRL:
            res = i1 >> shamt
        case ShiftUnitFn.Fn.ROR:
            res = (i1 >> shamt) | (i1 << (xlen - shamt))
        case ShiftUnitFn.Fn.ROL:
            res = (i1 << shamt) | (i1 >> (xlen - shamt))
    return {"result": res & mask}


ops: dict[ShiftUnitFn.Fn, RecordIntDict] = {
    ShiftUnitFn.Fn.SLL: {
        "op_type": OpType.SHIFT,
        "funct3": Funct3.SLL,
    },
    ShiftUnitFn.Fn.SRL: {
        "op_type": OpType.SHIFT,
        "funct3": Funct3.SR,
        "funct7": Funct7.SL,
    },
    ShiftUnitFn.Fn.SRA: {
        "op_type": OpType.SHIFT,
        "funct3": Funct3.SR,
        "funct7": Funct7.SA,
    },
    ShiftUnitFn.Fn.ROL: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.ROL,
        "funct7": Funct7.ROL,
    },
    ShiftUnitFn.Fn.ROR: {
        "op_type": OpType.BIT_MANIPULATION,
        "funct3": Funct3.ROR,
        "funct7": Funct7.ROR,
    },
}


class ShiftUnitTest(FunctionalUnitTestCase[ShiftUnitFn.Fn]):
    def test_test(self):
        self.run_fu_test()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ShiftUnitComponent(zbb_enable=True),
            compute_result,
            gen=GenParams(test_core_config),
            method_name=method_name,
            zero_imm=False,
        )
