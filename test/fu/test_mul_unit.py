from parameterized import parameterized_class
from typing import Dict

from coreblocks.params import *
from coreblocks.fu.mul_unit import MulFn, MulFU, MulType
from coreblocks.params.fu_params import FuncUnitParams

from test.common import signed_to_int, int_to_signed, test_gen_params

from test.fu.functional_common import GenericFunctionalTestUnit


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: MulFn.Fn, xlen: int) -> Dict[str, int]:
    signed_i1 = signed_to_int(i1, xlen)
    signed_i2 = signed_to_int(i2, xlen)
    if fn == MulFn.Fn.MUL:
        return {"result": (i1 * i2) % (2**xlen)}
    elif fn == MulFn.Fn.MULH:
        return {"result": int_to_signed(signed_i1 * signed_i2, 2 * xlen) // (2**xlen)}
    elif fn == MulFn.Fn.MULHU:
        return {"result": i1 * i2 // (2**xlen)}
    elif fn == MulFn.Fn.MULHSU:
        return {"result": int_to_signed(signed_i1 * i2, 2 * xlen) // (2**xlen)}
    else:
        signed_half_i1 = signed_to_int(i1 % (2 ** (xlen // 2)), xlen // 2)
        signed_half_i2 = signed_to_int(i2 % (2 ** (xlen // 2)), xlen // 2)
        return {"result": int_to_signed(signed_half_i1 * signed_half_i2, xlen)}


ops = {
    MulFn.Fn.MUL: {"op_type": OpType.MUL, "funct3": Funct3.MUL, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULH: {"op_type": OpType.MUL, "funct3": Funct3.MULH, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULHU: {"op_type": OpType.MUL, "funct3": Funct3.MULHU, "funct7": Funct7.MULDIV},
    MulFn.Fn.MULHSU: {"op_type": OpType.MUL, "funct3": Funct3.MULHSU, "funct7": Funct7.MULDIV},
    #  Prepared for RV64
    #
    #  MulFn.Fn.MULW: {"op_type": OpType.ARITHMETIC_W, "funct3": Funct3.MULW, "funct7": Funct7.MULDIV},
}


def gen_test_params(param):
    pass


@parameterized_class(
    ("name", "mul_unit"),
    [
        (
            "recursive_multiplier",
            MulFU(MulType.RECURSIVE_MUL, dsp_width=8),
        ),
        (
            "sequential_multiplier",
            MulFU(MulType.SEQUENCE_MUL, dsp_width=8),
        ),
        (
            "shift_multiplier",
            MulFU(MulType.SHIFT_MUL),
        ),
    ],
)
class MultiplierUnitTest(GenericFunctionalTestUnit):
    mul_unit: FuncUnitParams

    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            self.mul_unit,
            compute_result,
            gen=test_gen_params("rv32im"),
            number_of_tests=600,
            seed=32323,
            method_name=method_name,
        )
