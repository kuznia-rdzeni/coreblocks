from coreblocks.params import Funct3, Funct7, OpType
from coreblocks.fu.shift_unit import ShiftUnitFn, ShiftUnitComponent

from test.fu.functional_common import FunctionalUnitTestCase


class ShiftUnitTest(FunctionalUnitTestCase[ShiftUnitFn.Fn]):
    func_unit = ShiftUnitComponent(zbb_enable=True)
    zero_imm = False

    ops = {
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

    @staticmethod
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

    def test_fu(self):
        self.run_fu_test()
