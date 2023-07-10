from coreblocks.params import Funct3, Funct7
from coreblocks.fu.zbs import ZbsFunction, ZbsComponent
from test.common import RecordIntDict

from test.fu.functional_common import FunctionalUnitTestCase


@staticmethod
def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbsFunction.Fn, xlen: int) -> dict[str, int]:
    val2 = i_imm if i_imm else i2

    if fn == ZbsFunction.Fn.BCLR:
        index = val2 & (xlen - 1)
        return {"result": i1 & ~(1 << index)}
    if fn == ZbsFunction.Fn.BEXT:
        index = val2 & (xlen - 1)
        return {"result": (i1 >> index) & 1}
    if fn == ZbsFunction.Fn.BINV:
        index = val2 & (xlen - 1)
        return {"result": i1 ^ (1 << index)}
    if fn == ZbsFunction.Fn.BSET:
        index = val2 & (xlen - 1)
        return {"result": i1 | (1 << index)}


ops: dict[ZbsFunction.Fn, RecordIntDict] = {
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


class ZbsUnitTest(FunctionalUnitTestCase[ZbsFunction.Fn]):
    ops = ops
    func_unit = ZbsComponent()
    compute_result = compute_result
    zero_imm = False

    def test_test(self):
        self.run_fu_test()
