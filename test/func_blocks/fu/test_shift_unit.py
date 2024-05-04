from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.shift_unit import ShiftUnitFn, ShiftUnitComponent

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class TestShiftUnit(FunctionalUnitTestCase[ShiftUnitFn.Fn]):
    func_unit = ShiftUnitComponent(zbb_enable=True)
    zero_imm = False

    ops = {
        ShiftUnitFn.Fn.SLL: ExecFn(OpType.SHIFT, Funct3.SLL),
        ShiftUnitFn.Fn.SRL: ExecFn(OpType.SHIFT, Funct3.SR, Funct7.SL),
        ShiftUnitFn.Fn.SRA: ExecFn(OpType.SHIFT, Funct3.SR, Funct7.SA),
        ShiftUnitFn.Fn.ROL: ExecFn(OpType.BIT_ROTATION, Funct3.ROL, Funct7.ROL),
        ShiftUnitFn.Fn.ROR: ExecFn(OpType.BIT_ROTATION, Funct3.ROR, Funct7.ROR),
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
        self.run_standard_fu_test()

    def test_pipeline(self):
        self.run_standard_fu_test(pipeline_test=True)
