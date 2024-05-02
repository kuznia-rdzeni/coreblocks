from parameterized import parameterized_class

from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.mul_unit import MulFn, MulComponent, MulType

from transactron.utils import signed_to_int, int_to_signed

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


@parameterized_class(
    ("name", "func_unit"),
    [
        (
            "recursive_multiplier",
            MulComponent(MulType.RECURSIVE_MUL, dsp_width=8),
        ),
        (
            "sequential_multiplier",
            MulComponent(MulType.SEQUENCE_MUL, dsp_width=8),
        ),
        (
            "shift_multiplier",
            MulComponent(MulType.SHIFT_MUL),
        ),
    ],
)
class TestMultiplierUnit(FunctionalUnitTestCase[MulFn.Fn]):
    ops = {
        MulFn.Fn.MUL: ExecFn(OpType.MUL, Funct3.MUL, Funct7.MULDIV),
        MulFn.Fn.MULH: ExecFn(OpType.MUL, Funct3.MULH, Funct7.MULDIV),
        MulFn.Fn.MULHU: ExecFn(OpType.MUL, Funct3.MULHU, Funct7.MULDIV),
        MulFn.Fn.MULHSU: ExecFn(OpType.MUL, Funct3.MULHSU, Funct7.MULDIV),
        #  Prepared for RV64
        #
        #  MulFn.Fn.MULW: ExecFn(OpType.ARITHMETIC_W, Funct3.MULW, Funct7.MULDIV),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: MulFn.Fn, xlen: int) -> dict[str, int]:
        signed_i1 = signed_to_int(i1, xlen)
        signed_i2 = signed_to_int(i2, xlen)

        match fn:
            case MulFn.Fn.MUL:
                return {"result": (i1 * i2) % (2**xlen)}
            case MulFn.Fn.MULH:
                return {"result": int_to_signed(signed_i1 * signed_i2, 2 * xlen) // (2**xlen)}
            case MulFn.Fn.MULHU:
                return {"result": i1 * i2 // (2**xlen)}
            case MulFn.Fn.MULHSU:
                return {"result": int_to_signed(signed_i1 * i2, 2 * xlen) // (2**xlen)}
            case _:
                signed_half_i1 = signed_to_int(i1 % (2 ** (xlen // 2)), xlen // 2)
                signed_half_i2 = signed_to_int(i2 % (2 ** (xlen // 2)), xlen // 2)
                return {"result": int_to_signed(signed_half_i1 * signed_half_i2, xlen)}

    def test_fu(self):
        self.run_standard_fu_test()
