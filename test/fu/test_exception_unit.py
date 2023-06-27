from amaranth import *
from typing import Dict, Callable, Any
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.exception import ExceptionUnitFn, ExceptionUnitComponent
from coreblocks.params.configurations import test_core_config
from coreblocks.params.isa import ExceptionCause

from test.fu.functional_common import GenericFunctionalTestUnit


@staticmethod
def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ExceptionUnitFn.Fn, xlen: int) -> Dict[str, int]:
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


ops = {
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
class ExceptionUnitTest(GenericFunctionalTestUnit):
    compute_result: Callable[[int, int, int, int, Any, int], Dict[str, int]]

    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            self.ops,
            self.func_unit,
            self.compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=10,
            seed=32323,
            zero_imm=False,
            method_name=method_name,
        )
