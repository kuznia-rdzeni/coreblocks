from coreblocks.func_blocks.fu.exception import ExceptionUnitFn, ExceptionUnitComponent
from coreblocks.arch import ExceptionCause, Funct3
from coreblocks.arch import OpType

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class TestExceptionUnit(FunctionalUnitTestCase[ExceptionUnitFn.Fn]):
    func_unit = ExceptionUnitComponent()
    number_of_tests = 1
    zero_imm = False

    ops = {
        ExceptionUnitFn.Fn.EBREAK: ExecFn(OpType.EBREAK),
        ExceptionUnitFn.Fn.ECALL: ExecFn(OpType.ECALL),
        ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT: ExecFn(OpType.EXCEPTION, Funct3._EINSTRACCESSFAULT),
        ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION: ExecFn(OpType.EXCEPTION, Funct3._EILLEGALINSTR),
        ExceptionUnitFn.Fn.BREAKPOINT: ExecFn(OpType.EXCEPTION, Funct3._EBREAKPOINT),
        ExceptionUnitFn.Fn.INSTR_PAGE_FAULT: ExecFn(OpType.EXCEPTION, Funct3._EINSTRPAGEFAULT),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ExceptionUnitFn.Fn, xlen: int) -> dict[str, int]:
        cause = None

        match fn:
            case ExceptionUnitFn.Fn.EBREAK | ExceptionUnitFn.Fn.BREAKPOINT:
                cause = ExceptionCause.BREAKPOINT
            case ExceptionUnitFn.Fn.ECALL:
                cause = ExceptionCause.ENVIRONMENT_CALL_FROM_M
            case ExceptionUnitFn.Fn.INSTR_ACCESS_FAULT:
                cause = ExceptionCause.INSTRUCTION_ACCESS_FAULT
            case ExceptionUnitFn.Fn.INSTR_PAGE_FAULT:
                cause = ExceptionCause.INSTRUCTION_PAGE_FAULT
            case ExceptionUnitFn.Fn.ILLEGAL_INSTRUCTION:
                cause = ExceptionCause.ILLEGAL_INSTRUCTION

        return {"result": 0} | {"exception": cause} if cause is not None else {}

    def test_fu(self):
        self.run_standard_fu_test()
