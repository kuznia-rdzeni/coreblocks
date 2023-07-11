from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.mul_unit import MulFn, MulComponent, MulType

from test.common import signed_to_int, int_to_signed

from test.fu.functional_common import FunctionalUnitTestCase


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
class MultiplierUnitTest(FunctionalUnitTestCase[MulFn.Fn]):
    ops = {
        MulFn.Fn.MUL: {"op_type": OpType.MUL, "funct3": Funct3.MUL, "funct7": Funct7.MULDIV},
        MulFn.Fn.MULH: {"op_type": OpType.MUL, "funct3": Funct3.MULH, "funct7": Funct7.MULDIV},
        MulFn.Fn.MULHU: {"op_type": OpType.MUL, "funct3": Funct3.MULHU, "funct7": Funct7.MULDIV},
        MulFn.Fn.MULHSU: {"op_type": OpType.MUL, "funct3": Funct3.MULHSU, "funct7": Funct7.MULDIV},
        #  Prepared for RV64
        #
        #  MulFn.Fn.MULW: {"op_type": OpType.ARITHMETIC_W, "funct3": Funct3.MULW, "funct7": Funct7.MULDIV},
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
