from parameterized import parameterized_class

from coreblocks.params import Funct3, Funct7, OpType
from coreblocks.fu.div_unit import DivFn, DivComponent

from test.fu.functional_common import FunctionalUnitTestCase

from test.common import RecordIntDict, signed_to_int, int_to_signed


@parameterized_class(
    ("name", "func_unit"),
    [("ipc" + str(s), DivComponent(ipc=s)) for s in [3, 4, 5, 8]],
)
class DivisionUnitTest(FunctionalUnitTestCase[DivFn.Fn]):
    ops: dict[DivFn.Fn, RecordIntDict] = {
        DivFn.Fn.DIVU: {"op_type": OpType.DIV_REM, "funct3": Funct3.DIVU, "funct7": Funct7.MULDIV},
        DivFn.Fn.DIV: {"op_type": OpType.DIV_REM, "funct3": Funct3.DIV, "funct7": Funct7.MULDIV},
        DivFn.Fn.REMU: {"op_type": OpType.DIV_REM, "funct3": Funct3.REMU, "funct7": Funct7.MULDIV},
        DivFn.Fn.REM: {"op_type": OpType.DIV_REM, "funct3": Funct3.REM, "funct7": Funct7.MULDIV},
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: DivFn.Fn, xlen: int) -> dict[str, int]:
        signed_i1 = signed_to_int(i1, xlen)
        signed_i2 = signed_to_int(i2, xlen)

        res = 0
        mask = (1 << xlen) - 1

        match fn:
            case DivFn.Fn.DIVU:
                if i2 == 0:
                    res = -1
                else:
                    res = i1 // i2
            case DivFn.Fn.DIV:
                if signed_i2 == 0:
                    res = -1
                else:
                    res = abs(signed_i1) // abs(signed_i2)
                    # if signs are different negate the result
                    if signed_i1 * signed_i2 < 0:
                        res = int_to_signed(-res, xlen)
            case DivFn.Fn.REMU:
                if i2 == 0:
                    res = i1
                else:
                    res = i1 % i2
            case DivFn.Fn.REM:
                if signed_i2 == 0:
                    res = i1
                else:
                    res = abs(signed_i1) % abs(signed_i2)
                    # if divisor is negative negate the result
                    if signed_i1 < 0:
                        res = int_to_signed(-res, xlen)

        return {"result": res & mask}

    def test_fu(self):
        self.run_standard_fu_test()
