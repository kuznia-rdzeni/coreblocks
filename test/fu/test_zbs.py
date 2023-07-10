from coreblocks.params import Funct3, Funct7
from coreblocks.fu.zbs import ZbsFunction, ZbsComponent

from test.fu.functional_common import FunctionalUnitTestCase


class ZbsUnitTest(FunctionalUnitTestCase[ZbsFunction.Fn]):
    func_unit = ZbsComponent()
    zero_imm = False

    ops = {
        ZbsFunction.Fn.BCLR: {
            "funct3": Funct3.BCLR,
            "funct7": Funct7.BCLR,
        },
        ZbsFunction.Fn.BEXT: {
            "funct3": Funct3.BEXT,
            "funct7": Funct7.BEXT,
        },
        ZbsFunction.Fn.BINV: {
            "funct3": Funct3.BINV,
            "funct7": Funct7.BINV,
        },
        ZbsFunction.Fn.BSET: {
            "funct3": Funct3.BSET,
            "funct7": Funct7.BSET,
        },
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
        self.run_fu_test()
