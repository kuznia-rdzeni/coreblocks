from amaranth import *
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn, JumpComponent
from transactron import Method, def_method, TModule
from coreblocks.params.layouts import FuncUnitLayouts, FetchLayouts
from coreblocks.utils.protocols import FuncUnit

from transactron._utils import signed_to_int

from test.fu.functional_common import ExecFn, FunctionalUnitTestCase


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.jb = JumpBranchFuncUnit(gen_params)
        self.issue = self.jb.issue
        self.accept = Method(o=gen_params.get(FuncUnitLayouts).accept + gen_params.get(FetchLayouts).branch_verify)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.jb_unit = self.jb

        @def_method(m, self.accept)
        def _(arg):
            res = self.jb.accept(m)
            br = self.jb.branch_result(m)
            return {
                "from_pc": br.from_pc,
                "next_pc": br.next_pc,
                "resume_from_exception": 0,
                "result": res.result,
                "rob_id": res.rob_id,
                "rp_dst": res.rp_dst,
                "exception": res.exception,
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

    exception = None
    if next_pc & 0b11 != 0:
        exception = ExceptionCause.INSTRUCTION_ADDRESS_MISALIGNED

    return {"result": res, "from_pc": pc, "next_pc": next_pc, "resume_from_exception": 0} | (
        {"exception": exception} if exception is not None else {}
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
class JumpBranchUnitTest(FunctionalUnitTestCase[JumpBranchFn.Fn]):
    compute_result = compute_result
    zero_imm = False

    def test_fu(self):
        self.run_standard_fu_test()
