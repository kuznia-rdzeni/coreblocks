from parameterized import parameterized_class

from coreblocks.func_blocks.fu.zbc import ZbcFn, ZbcComponent
from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.params.configurations import test_core_config

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


# Instruction semantics are based on pseudocode from the spec
# https://github.com/riscv/riscv-bitmanip/releases/download/1.0.0/bitmanip-1.0.0-38-g865e7a7.pdf
def clmul(i1: int, i2: int, xlen: int) -> int:
    output = 0
    for i in range(xlen + 1):
        if (i2 >> i) & 1 == 1:
            output ^= i1 << i
    return output % (2**xlen)


def clmulh(i1: int, i2: int, xlen: int) -> int:
    output = 0
    for i in range(1, xlen + 1):
        if (i2 >> i) & 1 == 1:
            output ^= i1 >> (xlen - i)
    return output % (2**xlen)


def clmulr(i1: int, i2: int, xlen: int) -> int:
    output = 0
    for i in range(xlen):
        if (i2 >> i) & 1 == 1:
            output ^= i1 >> (xlen - i - 1)
    return output % (2**xlen)


@parameterized_class(
    ("name", "func_unit"),
    [
        (
            "iterative",
            ZbcComponent(recursion_depth=0),
        ),
        (
            "recursive_3",
            ZbcComponent(recursion_depth=3),
        ),
        (
            "recursive_full",
            ZbcComponent(recursion_depth=test_core_config.xlen.bit_length() - 1),
        ),
    ],
)
class TestZbcUnit(FunctionalUnitTestCase[ZbcFn.Fn]):
    ops = {
        ZbcFn.Fn.CLMUL: ExecFn(OpType.CLMUL, Funct3.CLMUL, Funct7.CLMUL),
        ZbcFn.Fn.CLMULH: ExecFn(OpType.CLMUL, Funct3.CLMULH, Funct7.CLMUL),
        ZbcFn.Fn.CLMULR: ExecFn(OpType.CLMUL, Funct3.CLMULR, Funct7.CLMUL),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbcFn.Fn, xlen: int) -> dict[str, int]:
        match fn:
            case ZbcFn.Fn.CLMUL:
                return {"result": clmul(i1, i2, xlen)}
            case ZbcFn.Fn.CLMULH:
                return {"result": clmulh(i1, i2, xlen)}
            case ZbcFn.Fn.CLMULR:
                return {"result": clmulr(i1, i2, xlen)}

    def test_fu(self):
        self.run_standard_fu_test()
