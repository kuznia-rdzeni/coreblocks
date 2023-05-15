from coreblocks.params import Funct3, Funct7, GenParams, OpType
from coreblocks.params.configurations import test_core_config
from coreblocks.fu.alu import AluFn, ALUComponent

from test.fu.functional_common import GenericFunctionalTestUnit

def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: AluFn.Fn, xlen: int) -> dict[str, int]:
    val2 = i_imm if i_imm else i2
    mask = (1 << xlen) - 1

    res = 0

    if fn == AluFn.Fn.ADD:
        res = (i1 + val2)

    if fn == AluFn.Fn.SUB:
        res = i1 - val2

    if fn == AluFn.Fn.XOR:
        res = i1 ^ val2

    if fn == AluFn.Fn.OR:
        res = i1 | val2

    if fn == AluFn.Fn.AND:
        res = i1 & val2

    if fn == AluFn.Fn.SLT:
        def _cast_to_int_xlen(x):
            if xlen == 32:
                return -int(0x100000000 - x) if (x > 0x7FFFFFFF) else x
            elif xlen == 64:
                return -int(0x10000000000000000 - x) if (x > 0x7FFFFFFFFFFFFFFF) else x
            return 0

        res = _cast_to_int_xlen(i1) < _cast_to_int_xlen(val2)

    if fn == AluFn.Fn.SLTU:
        res = i1 < val2

    if fn == AluFn.Fn.SH1ADD:
        res = (i1 << 1) + val2

    if fn == AluFn.Fn.SH2ADD:
        res = (i1 << 2) + val2

    if fn == AluFn.Fn.SH3ADD:
       res = (i1 << 3) + val2

    return {"result": res & mask}


ops = {
    AluFn.Fn.ADD: {
        "op_type": OpType.ARITHMETIC,
        "funct3": Funct3.ADD,
        "funct7": Funct7.ADD,
    },
    AluFn.Fn.SUB: {
        "op_type": OpType.ARITHMETIC,
        "funct3": Funct3.ADD,
        "funct7": Funct7.SUB,
    },
    AluFn.Fn.SLT: {
        "op_type": OpType.COMPARE,
        "funct3": Funct3.SLT,
    },
    AluFn.Fn.SLTU: {
        "op_type": OpType.COMPARE,
        "funct3": Funct3.SLTU,
    },
    AluFn.Fn.XOR: {
        "op_type": OpType.LOGIC,
        "funct3": Funct3.XOR,
    },
    AluFn.Fn.OR: {
        "op_type": OpType.LOGIC,
        "funct3": Funct3.OR,
    },
    AluFn.Fn.AND: {
        "op_type": OpType.LOGIC,
        "funct3": Funct3.AND,
    },
    AluFn.Fn.SH1ADD: {
        "op_type": OpType.ADDRESS_GENERATION,
        "funct3": Funct3.SH1ADD,
        "funct7": Funct7.SH1ADD,
    },
    AluFn.Fn.SH2ADD: {
        "op_type": OpType.ADDRESS_GENERATION,
        "funct3": Funct3.SH2ADD,
        "funct7": Funct7.SH2ADD,
    },
    AluFn.Fn.SH3ADD: {
        "op_type": OpType.ADDRESS_GENERATION,
        "funct3": Funct3.SH3ADD,
        "funct7": Funct7.SH3ADD,
    },
}


class ShiftUnitTest(GenericFunctionalTestUnit):
    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            ops,
            ALUComponent(zba_enable=True),
            compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=800,
            seed=42,
            method_name=method_name,
            zero_imm=False,
        )
