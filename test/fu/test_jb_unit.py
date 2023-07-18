from amaranth import *
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn, JumpComponent
from coreblocks.transactions import Method, Transaction, TModule
from coreblocks.transactions.lib import FIFO
from coreblocks.params.layouts import FuncUnitLayouts, FetchLayouts
from coreblocks.utils.protocols import FuncUnit
from coreblocks.utils.utils import assign

from test.common import signed_to_int

from test.fu.functional_common import ExecFn, FunctionalUnitTestCase


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams, send_result: Method):
        self.gen_params = gen_params
        self.send_result = send_result
        self.issue = Method(i=self.gen_params.get(FuncUnitLayouts).issue)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.fifo = fifo = FIFO(self.gen_params.get(FuncUnitLayouts).send_result, 2)

        m.submodules.jb_unit = self.jb = JumpBranchFuncUnit(self.gen_params, send_result=fifo.write)

        self.issue.proxy(m, self.jb.issue)

        with Transaction().body(m):
            new_arg = Record.like(self.send_result.data_in)
            m.d.comb += assign(new_arg, fifo.read(m))
            m.d.comb += assign(new_arg, self.jb.branch_result(m))
            self.send_result(m, new_arg)

        return m


class JumpBranchWrapperComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams, send_result: Method) -> FuncUnit:
        return JumpBranchWrapper(gen_params, send_result)

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

    return {"result": res, "from_pc": pc, "next_pc": next_pc} | (
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
    ("name", "ops", "func_unit", "compute_result", "result_layout_additional"),
    [
        (
            "branches_and_jumps",
            ops,
            JumpBranchWrapperComponent(),
            compute_result,
            lambda _, gen: gen.get(FetchLayouts).branch_verify,
        ),
        ("auipc", ops_auipc, JumpComponent(), compute_result_auipc, lambda _, gen: []),
    ],
)
class JumpBranchUnitTest(FunctionalUnitTestCase[JumpBranchFn.Fn]):
    compute_result = compute_result
    zero_imm = False

    def test_fu(self):
        self.run_standard_fu_test()
