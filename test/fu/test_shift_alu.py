from coreblocks.params import Funct3, Funct7, GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.fu.shift_alu import ShiftAluFn, ShiftALUComponent

from test.fu.functional_common import GenericFunctionalTestUnit


def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ShiftAluFn.Fn, xlen: int) -> dict[str, int]:
    val2 = i_imm if i_imm else i2

    mask = (1 << xlen) - 1

    if fn == ShiftAluFn.Fn.SLL:
        res = i1 << (val2 & (xlen - 1))

        return { "result": res & mask }

    if fn == ShiftAluFn.Fn.SRA:
        val2 = val2 & (xlen - 1)
        res = 0
        if i1 & 2 ** (xlen - 1) != 0:
            res =  (((1 << xlen) - 1) << xlen | i1) >> val2
        else:
            res =  i1 >> val2
        return {"result": res & mask}

    if fn == ShiftAluFn.Fn.SRL:
        res = i1 >> (val2 & (xlen - 1))
        return {"result": res & mask}


ops = {
    ShiftAluFn.Fn.SLL: {
        "funct3": Funct3.SLL,
    },
    ShiftAluFn.Fn.SRL: {
        "funct3": Funct3.SR,
        "funct7": Funct7.SL,
    },
    ShiftAluFn.Fn.SRA: {
        "funct3": Funct3.SR,
        "funct7": Funct7.SA,
    },
}


class ShiftUnitTest(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ShiftALUComponent(),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=100,
            seed=42,
            method_name=method_name,
            zero_imm=False,
        )
