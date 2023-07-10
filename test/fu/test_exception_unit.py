from amaranth import *
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.exception import ExceptionUnitFn, ExceptionUnitComponent
from coreblocks.params.isa import ExceptionCause
from test.common import RecordIntDict

from test.fu.functional_common import FunctionalUnitTestCase


@staticmethod
def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ExceptionUnitFn.Fn, xlen: int) -> dict[str, int]:
    cause = None
    if fn == ExceptionUnitFn.Fn.EBREAK or fn == ExceptionUnitFn.Fn.BREAKPOINT:
        cause = ExceptionCause.BREAKPOINT
    if fn == ExceptionUnitFn.Fn.ECALL:
        cause = ExceptionCause.ENVIRONMENT_CALL_FROM_M
    if fn == ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT:
        cause = ExceptionCause.INSTRUCTION_ACCESS_FAULT
    if fn == ExceptionUnitFn.Fn.INSTR_PAGE_FAULT:
        cause = ExceptionCause.INSTRUCTION_PAGE_FAULT
    if fn == ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION:
        cause = ExceptionCause.ILLEGAL_INSTRUCTION

    return {"result": 0} | {"exception": cause} if cause is not None else {}


ops: dict[ExceptionUnitFn.Fn, RecordIntDict] = {
    ExceptionUnitFn.Fn.EBREAK: {"op_type": OpType.EBREAK},
    ExceptionUnitFn.Fn.ECALL: {"op_type": OpType.ECALL},
    ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT: {"op_type": OpType.EXCEPTION, "funct3": Funct3._EINSTRACCESSFAULT},
    ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION: {"op_type": OpType.EXCEPTION, "funct3": Funct3._EILLEGALINSTR},
    ExceptionUnitFn.Fn.BREAKPOINT: {"op_type": OpType.EXCEPTION, "funct3": Funct3._EBREAKPOINT},
    ExceptionUnitFn.Fn.INSTR_PAGE_FAULT: {"op_type": OpType.EXCEPTION, "funct3": Funct3._EINSTRPAGEFAULT},
}


@parameterized_class(
    ("name", "ops", "func_unit", "compute_result"),
    [
        (
            "excpetions_fu",
            ops,
            ExceptionUnitComponent(),
            compute_result,
        )
    ],
)
class ExceptionUnitTest(FunctionalUnitTestCase[ExceptionUnitFn.Fn]):
    number_of_tests = 1
    zero_imm = False

    def test_test(self):
        self.run_fu_test()
