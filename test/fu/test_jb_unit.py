from amaranth import *
from parameterized import parameterized_class
from collections import deque

from coreblocks.params import *
from coreblocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn
from transactron import TModule
from transactron.lib import Adapter, AdapterTrans
from coreblocks.params.layouts import FetchLayouts
from coreblocks.utils.protocols import FuncUnit

from test.common import signed_to_int, TestbenchIO, def_method_mock

from test.fu.functional_common import ExecFn, FunctionalUnitTestCase


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams):
        fetch_layouts = gen_params.get(FetchLayouts)
        self.set_pc = TestbenchIO(Adapter(i=fetch_layouts.branch_verify_in, o=fetch_layouts.branch_verify_out))
        gen_params.get(DependencyManager).add_dependency(BranchResolvedKey(), self.set_pc.adapter.iface)

        self.jb = JumpBranchFuncUnit(gen_params)

        self.precommit = TestbenchIO(AdapterTrans(self.jb.precommit))

        self.issue = self.jb.issue
        self.accept = self.jb.accept
        self.clear = self.jb.clear
        self.optypes = set()

    def elaborate(self, platform):
        m = TModule()

        m.submodules.jb_unit = self.jb
        m.submodules.set_pc = self.set_pc
        m.submodules.precommit = self.precommit

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
    ("name", "ops", "compute_result"),
    [
        (
            "branches_and_jumps",
            ops,
            compute_result,
        ),
        (
            "auipc",
            ops_auipc,
            compute_result_auipc,
        ),
    ],
)
class JumpBranchUnitTest(FunctionalUnitTestCase[JumpBranchFn.Fn]):
    compute_result = compute_result
    zero_imm = False
    number_of_tests = 300
    func_unit = JumpBranchWrapperComponent()

    def test_test(self):
        precommit_q = deque()
        # it's either ignoring the type or forcing 'precommit' to exist in all FUs
        fu: JumpBranchWrapper = self.m.func_unit  # type: ignore

        def main_proc():
            while self.requests:
                # JB unit is serialized now anyway so this doesn't hurt
                req = self.requests.pop()
                yield from self.m.issue.call(req)
                yield from fu.precommit.call({"rob_id": req["rob_id"]})
                res = yield from self.m.accept.call()
                if req["exec_fn"]["op_type"] != OpType.AUIPC:
                    res |= precommit_q.pop()
                expected = self.responses.pop()
                self.assertDictEqual(res, expected)

        @def_method_mock(lambda: fu.set_pc, sched_prio=0, enable=lambda: True)
        def set_pc_mock(arg):
            precommit_q.append(arg)
            return {"old_pc": 0}

        exception_consumer = self.get_basic_processes()["exception_consumer"]
        self.run_pipeline(
            {"main_proc": main_proc, "set_pc_mock": set_pc_mock, "exception_consumer": exception_consumer}
        )
