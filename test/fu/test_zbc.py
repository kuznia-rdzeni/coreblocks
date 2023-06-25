from typing import Dict

from coreblocks.fu.zbc import ZbcFn, ZbcComponent
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config

from test.fu.functional_common import GenericFunctionalTestUnit


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


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbcFn.Fn, xlen: int) -> Dict[str, int]:
    match fn:
        case ZbcFn.Fn.CLMUL:
            return {"result": clmul(i1, i2, xlen)}
        case ZbcFn.Fn.CLMULH:
            return {"result": clmulh(i1, i2, xlen)}
        case ZbcFn.Fn.CLMULR:
            return {"result": clmulr(i1, i2, xlen)}


ops = {
    ZbcFn.Fn.CLMUL: {"op_type": OpType.CLMUL, "funct3": Funct3.CLMUL, "funct7": Funct7.CLMUL},
    ZbcFn.Fn.CLMULH: {"op_type": OpType.CLMUL, "funct3": Funct3.CLMULH, "funct7": Funct7.CLMUL},
    ZbcFn.Fn.CLMULR: {"op_type": OpType.CLMUL, "funct3": Funct3.CLMULR, "funct7": Funct7.CLMUL},
}


class IterativeZbcUnitTest(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ZbcComponent(recursion_depth=0),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=400,
            seed=323262,
            method_name=method_name,
        )


class RecursiveZbcUnitTestDepth3(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ZbcComponent(recursion_depth=3),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=400,
            seed=323262,
            method_name=method_name,
        )


class RecursiveZbcUnitTestFullDepth(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        gen = GenParams(test_core_config)
        super().__init__(
            ops,
            ZbcComponent(recursion_depth=gen.isa.xlen_log),
            compute_result,
            gen=gen,
            number_of_tests=300,
            seed=323262,
            method_name=method_name,
        )
