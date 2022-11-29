from coreblocks.isa import OpType, Funct3, Funct7
from coreblocks.mul_unit import MulUnit, MulFn

from .common import signed_to_int, int_to_signed

from .functional_common import GenericFunctionalTestUnit


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


class Test(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, methodName: str = "runTest"):
        super().__init__(ops, MulUnit, compute_result, methodName=methodName)
