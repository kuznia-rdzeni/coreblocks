from coreblocks.params import Funct3, Funct7, OpType, GenParams
from coreblocks.fu.division_unit import DivFn, DivComponent

from test.fu.functional_common import GenericFunctionalTestUnit
from coreblocks.params.configurations import test_core_config


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: DivFn.Fn, xlen: int) -> dict[str, int]:
    # signed_i1 = signed_to_int(i1, xlen)
    # signed_i2 = signed_to_int(i2, xlen)

    res = 0
    mask = (1 << xlen) - 1

    match fn:
        case DivFn.Fn.DIV:
            res = i1 // i2
        case DivFn.Fn.REM:
            res = i1 % i2

    return {"result": res & mask}


ops = {
    DivFn.Fn.DIV: {"op_type": OpType.DIV_REM, "funct3": Funct3.DIV, "funct7": Funct7.MULDIV},
    DivFn.Fn.REM: {"op_type": OpType.DIV_REM, "funct3": Funct3.REM, "funct7": Funct7.MULDIV},
}


class DivisionUnitTest(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            DivComponent(),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=100,
            seed=1,
            method_name=method_name,
        )
