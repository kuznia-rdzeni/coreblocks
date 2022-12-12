from parameterized import parameterized_class

from coreblocks.params import OpType, Funct3, Funct7, GenParams
from coreblocks.fu.mul_unit import MulUnit, MulFn
from coreblocks.params.mul_params import MulUnitParams

from test.common import signed_to_int, int_to_signed

from test.fu.functional_common import GenericFunctionalTestUnit


def compute_result(i1: int, i2: int, fn: MulFn.Fn, xlen: int) -> int:
    signed_i1 = signed_to_int(i1, xlen)
    signed_i2 = signed_to_int(i2, xlen)
    if fn == MulFn.Fn.MUL:
        return (i1 * i2) % (2**xlen)
    elif fn == MulFn.Fn.MULH:
        return int_to_signed(signed_i1 * signed_i2, 2 * xlen) // (2**xlen)
    elif fn == MulFn.Fn.MULHU:
        return i1 * i2 // (2**xlen)
    elif fn == MulFn.Fn.MULHSU:
        return int_to_signed(signed_i1 * i2, 2 * xlen) // (2**xlen)
    else:
        signed_half_i1 = signed_to_int(i1 % (2 ** (xlen // 2)), xlen // 2)
        signed_half_i2 = signed_to_int(i2 % (2 ** (xlen // 2)), xlen // 2)
        return int_to_signed(signed_half_i1 * signed_half_i2, xlen)


ops = {
    MulFn.Fn.MUL: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MUL, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULH: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MULH, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULHU: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MULHU, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULHSU: {"op_type": OpType.ARITHMETIC, "funct3": Funct3.MULHSU, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULW: {"op_type": OpType.ARITHMETIC_W, "funct3": Funct3.MULW, "funct7": Funct7.MULDIV},
}


@parameterized_class(
    ("name", "gen_params"),
    [
        (
            "recursive_multiplier",
            GenParams("rv64im", mul_unit_params=MulUnitParams.RecursiveMultiplier(32)),
        ),
        (
            "sequential_multiplier",
            GenParams("rv64im", mul_unit_params=MulUnitParams.SequenceMultiplier(16)),
        ),
        (
            "shift_multiplier",
            GenParams("rv64im", mul_unit_params=MulUnitParams.ShiftMultiplier()),
        ),
    ],
)
class MultiplierUnitTest(GenericFunctionalTestUnit):
    gen_params: GenParams

    def test_test(self):
        self.run_pipeline()

    def __init__(self, methodName: str = "runTest"):
        super().__init__(
            ops, MulUnit, compute_result, gen=self.gen_params, number_of_tests=600, seed=32323, methodName=methodName
        )
