from coreblocks.params import Funct3, Funct7
from coreblocks.fu.zbs import ZbsFunction, ZbsComponent
from test.common import test_gen_params

from test.fu.functional_common import GenericFunctionalTestUnit


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbsFunction.Function, xlen: int) -> dict[str, int]:
    val2 = i_imm if i_imm else i2

    if fn == ZbsFunction.Function.BCLR:
        index = val2 & (xlen - 1)
        return {"result": i1 & ~(1 << index)}
    if fn == ZbsFunction.Function.BEXT:
        index = val2 & (xlen - 1)
        return {"result": (i1 >> index) & 1}
    if fn == ZbsFunction.Function.BINV:
        index = val2 & (xlen - 1)
        return {"result": i1 ^ (1 << index)}
    if fn == ZbsFunction.Function.BSET:
        index = val2 & (xlen - 1)
        return {"result": i1 | (1 << index)}


ops = {
    ZbsFunction.Function.BCLR: {
        "funct3": Funct3.BCLR,
        "funct7": Funct7.BCLR,
    },
    ZbsFunction.Function.BEXT: {
        "funct3": Funct3.BEXT,
        "funct7": Funct7.BEXT,
    },
    ZbsFunction.Function.BINV: {
        "funct3": Funct3.BINV,
        "funct7": Funct7.BINV,
    },
    ZbsFunction.Function.BSET: {
        "funct3": Funct3.BSET,
        "funct7": Funct7.BSET,
    },
}


class ZbsUnitTest(GenericFunctionalTestUnit):

    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ZbsComponent(),
            compute_result,
            gen=test_gen_params("rv32i"),
            number_of_tests=600,
            seed=32323,
            method_name=method_name,
            zero_imm=False,
        )
