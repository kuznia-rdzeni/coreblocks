from amaranth import *
from amaranth.lib.data import StructLayout
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.func_blocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn
from transactron import Method, def_method, TModule, Transaction

from coreblocks.interface.layouts import FuncUnitLayouts, JumpBranchLayouts
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.arch import Funct3, OpType, ExceptionCause
from coreblocks.interface.keys import PredictedJumpTargetKey

from transactron.utils import signed_to_int, DependencyContext
from transactron.lib import BasicFifo

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams, auipc_test: bool):
        self.gp = gen_params
        self.auipc_test = auipc_test
        layouts = gen_params.get(JumpBranchLayouts)

        self.target_pred_req = Method(i=layouts.predicted_jump_target_req)
        self.target_pred_resp = Method(o=layouts.predicted_jump_target_resp)

        DependencyContext.get().add_dependency(PredictedJumpTargetKey(), (self.target_pred_req, self.target_pred_resp))

        self.jb = JumpBranchFuncUnit(gen_params)
        self.issue = self.jb.issue
        self.accept = Method(o=StructLayout(gen_params.get(FuncUnitLayouts).accept.members))

    def elaborate(self, platform):
        m = TModule()

        m.submodules.jb_unit = self.jb
        m.submodules.res_fifo = res_fifo = BasicFifo(self.gp.get(FuncUnitLayouts).accept, 2)

        with Transaction().body(m):
            res_fifo.write(m, self.jb.accept(m))

        @def_method(m, self.target_pred_req)
        def _():
            pass

        @def_method(m, self.target_pred_resp)
        def _(arg):
            return {"valid": 0, "cfi_target": 0}

        @def_method(m, self.accept)
        def _(arg):
            res = res_fifo.read(m)
            ret = {
                "result": res.result,
                "rob_id": res.rob_id,
                "rp_dst": res.rp_dst,
                "exception": res.exception,
            }
            if self.auipc_test:
                return ret

            return ret

        return m


class JumpBranchWrapperComponent(FunctionalComponentParams):
    def __init__(self, auipc_test: bool):
        self.auipc_test = auipc_test

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return JumpBranchWrapper(gen_params, self.auipc_test)

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
            JumpBranchWrapperComponent(auipc_test=False),
            compute_result,
        ),
        (
            "auipc",
            ops_auipc,
            JumpBranchWrapperComponent(auipc_test=True),
            compute_result_auipc,
        ),
    ],
)
class TestJumpBranchUnit(FunctionalUnitTestCase[JumpBranchFn.Fn]):
    compute_result = compute_result
    zero_imm = False

    def test_fu(self):
        self.run_standard_fu_test()
