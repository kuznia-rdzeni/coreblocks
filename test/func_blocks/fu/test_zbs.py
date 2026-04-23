from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.zbs import ZbsFn, ZbsComponent

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class TestZbsUnit(FunctionalUnitTestCase[ZbsFn.Fn]):
    func_unit = ZbsComponent()
    zero_imm = False

    ops = {
        ZbsFn.Fn.BCLR: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BCLR, Funct7.BCLR),
        ZbsFn.Fn.BEXT: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BEXT, Funct7.BEXT),
        ZbsFn.Fn.BINV: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BINV, Funct7.BINV),
        ZbsFn.Fn.BSET: ExecFn(OpType.SINGLE_BIT_MANIPULATION, Funct3.BSET, Funct7.BSET),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbsFn.Fn, xlen: int) -> dict[str, int]:
        val2 = i_imm if i_imm else i2

        match fn:
            case ZbsFn.Fn.BCLR:
                index = val2 & (xlen - 1)
                return {"result": i1 & ~(1 << index)}
            case ZbsFn.Fn.BEXT:
                index = val2 & (xlen - 1)
                return {"result": (i1 >> index) & 1}
            case ZbsFn.Fn.BINV:
                index = val2 & (xlen - 1)
                return {"result": i1 ^ (1 << index)}
            case ZbsFn.Fn.BSET:
                index = val2 & (xlen - 1)
                return {"result": i1 | (1 << index)}

    def test_fu(self):
        self.run_standard_fu_test()

    def test_pipeline(self):
        self.run_standard_fu_test(pipeline_test=True)
