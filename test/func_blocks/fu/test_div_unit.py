from parameterized import parameterized_class

from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.div_unit import DivFn, DivComponent

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase

from transactron.utils import signed_to_int, int_to_signed


@parameterized_class(
    ("name", "func_unit"),
    [("ipc" + str(s), DivComponent(ipc=s)) for s in [3, 4, 5, 8]],
)
class TestDivisionUnit(FunctionalUnitTestCase[DivFn.Fn]):
    ops = {
        DivFn.Fn.DIVU: ExecFn(OpType.DIV_REM, Funct3.DIVU, Funct7.MULDIV),
        DivFn.Fn.DIV: ExecFn(OpType.DIV_REM, Funct3.DIV, Funct7.MULDIV),
        DivFn.Fn.REMU: ExecFn(OpType.DIV_REM, Funct3.REMU, Funct7.MULDIV),
        DivFn.Fn.REM: ExecFn(OpType.DIV_REM, Funct3.REM, Funct7.MULDIV),
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
