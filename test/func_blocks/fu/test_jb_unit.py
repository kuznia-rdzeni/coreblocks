from amaranth import *
from amaranth.lib.data import StructLayout
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.func_blocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn, JumpComponent
from transactron import Method, def_method, TModule
from coreblocks.interface.layouts import FuncUnitLayouts, JumpBranchLayouts
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.arch import Funct3, OpType, ExceptionCause

from transactron.utils import signed_to_int

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.jb = JumpBranchFuncUnit(gen_params)
        self.issue = self.jb.issue
        self.accept = Method(
            o=StructLayout(
                gen_params.get(FuncUnitLayouts).accept.members | gen_params.get(JumpBranchLayouts).verify_branch.members
            )
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.jb_unit = self.jb

        @def_method(m, self.accept)
        def _(arg):
            res = self.jb.accept(m)
            verify = self.jb.fifo_branch_resolved.read(m)
            return {
                "result": res.result,
                "rob_id": res.rob_id,
                "rp_dst": res.rp_dst,
                "exception": res.exception,
                "next_pc": verify.next_pc,
                "from_pc": verify.from_pc,
                "misprediction": verify.misprediction,
            }

        return m


class JumpBranchWrapperComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return JumpBranchWrapper(gen_params)

    def get_optypes(self) -> set[OpType]:
        return JumpBranchFn().get_op_types()


@staticmethod
def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: JumpBranchFn.Fn, xlen: int) -> dict[str, int]:
    max_int = 2**xlen - 1
    branch_target = pc + signed_to_int(i_imm & 0x1FFF, 13)
    next_pc = 0
    res = pc + 4

    match fn:
        case JumpBranchFn.Fn.JAL:
            next_pc = pc + signed_to_int(i_imm & 0x1FFFFF, 21)  # truncate to first 21 bits
        case JumpBranchFn.Fn.JALR:
            # truncate to first 12 bits and set 0th bit to 0
            next_pc = (i1 + signed_to_int(i_imm & 0xFFF, 12)) & ~0x1
        case JumpBranchFn.Fn.BEQ:
            next_pc = branch_target if i1 == i2 else pc + 4
        case JumpBranchFn.Fn.BNE:
            next_pc = branch_target if i1 != i2 else pc + 4
        case JumpBranchFn.Fn.BLT:
            next_pc = branch_target if signed_to_int(i1, xlen) < signed_to_int(i2, xlen) else pc + 4
        case JumpBranchFn.Fn.BLTU:
            next_pc = branch_target if i1 < i2 else pc + 4
        case JumpBranchFn.Fn.BGE:
            next_pc = branch_target if signed_to_int(i1, xlen) >= signed_to_int(i2, xlen) else pc + 4
        case JumpBranchFn.Fn.BGEU:
            next_pc = branch_target if i1 >= i2 else pc + 4

    next_pc &= max_int
    res &= max_int

    misprediction = next_pc != pc + 4

    exception = None
    exception_pc = pc
    if next_pc & 0b11 != 0:
        exception = ExceptionCause.INSTRUCTION_ADDRESS_MISALIGNED
    elif misprediction:
        exception = ExceptionCause._COREBLOCKS_MISPREDICTION
        exception_pc = next_pc

    return {"result": res, "from_pc": pc, "next_pc": next_pc, "misprediction": misprediction} | (
        {"exception": exception, "exception_pc": exception_pc} if exception is not None else {}
    )


@staticmethod
def compute_result_auipc(i1: int, i2: int, i_imm: int, pc: int, fn: JumpBranchFn.Fn, xlen: int) -> dict[str, int]:
    max_int = 2**xlen - 1
    res = pc + 4

    if fn == JumpBranchFn.Fn.AUIPC:
        res = pc + (i_imm & 0xFFFFF000)

    res &= max_int

    return {"result": res}


ops = {
    JumpBranchFn.Fn.BEQ: ExecFn(OpType.BRANCH, Funct3.BEQ),
    JumpBranchFn.Fn.BNE: ExecFn(OpType.BRANCH, Funct3.BNE),
    JumpBranchFn.Fn.BLT: ExecFn(OpType.BRANCH, Funct3.BLT),
    JumpBranchFn.Fn.BLTU: ExecFn(OpType.BRANCH, Funct3.BLTU),
    JumpBranchFn.Fn.BGE: ExecFn(OpType.BRANCH, Funct3.BGE),
    JumpBranchFn.Fn.BGEU: ExecFn(OpType.BRANCH, Funct3.BGEU),
    JumpBranchFn.Fn.JAL: ExecFn(OpType.JAL),
    JumpBranchFn.Fn.JALR: ExecFn(OpType.JALR),
}

ops_auipc = {
    JumpBranchFn.Fn.AUIPC: ExecFn(OpType.AUIPC),
}


@parameterized_class(
    ("name", "ops", "func_unit", "compute_result"),
    [
        (
            "branches_and_jumps",
            ops,
            JumpBranchWrapperComponent(),
            compute_result,
        ),
        (
            "auipc",
            ops_auipc,
            JumpComponent(),
            compute_result_auipc,
        ),
    ],
)
class TestJumpBranchUnit(FunctionalUnitTestCase[JumpBranchFn.Fn]):
    compute_result = compute_result
    zero_imm = False

    def test_fu(self):
        self.run_standard_fu_test()
