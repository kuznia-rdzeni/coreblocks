from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.zbs import ZbsFunction, ZbsComponent

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class TestZbsUnit(FunctionalUnitTestCase[ZbsFunction.Fn]):
    func_unit = ZbsComponent()
    zero_imm = False

    ops = {
        ZbsFunction.Fn.BCLR: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BCLR, Funct7.BCLR),
        ZbsFunction.Fn.BEXT: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BEXT, Funct7.BEXT),
        ZbsFunction.Fn.BINV: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BINV, Funct7.BINV),
        ZbsFunction.Fn.BSET: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BSET, Funct7.BSET),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbsFunction.Fn, xlen: int) -> dict[str, int]:
        val2 = i_imm if i_imm else i2

        match fn:
            case ZbsFunction.Fn.BCLR:
                index = val2 & (xlen - 1)
                return {"result": i1 & ~(1 << index)}
            case ZbsFunction.Fn.BEXT:
                index = val2 & (xlen - 1)
                return {"result": (i1 >> index) & 1}
            case ZbsFunction.Fn.BINV:
                index = val2 & (xlen - 1)
                return {"result": i1 ^ (1 << index)}
            case ZbsFunction.Fn.BSET:
                index = val2 & (xlen - 1)
                return {"result": i1 | (1 << index)}

    def test_fu(self):
        self.run_standard_fu_test()

    def test_pipeline(self):
        self.run_standard_fu_test(pipeline_test=True)
