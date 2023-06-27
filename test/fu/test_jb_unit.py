from amaranth import *
from typing import Dict, Callable, Any
from parameterized import parameterized_class
from collections import deque

from coreblocks.params import *
from coreblocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn
from coreblocks.transactions import TModule
from coreblocks.transactions.lib import Adapter, AdapterTrans
from coreblocks.params.configurations import test_core_config
from coreblocks.utils.protocols import FuncUnit

from test.common import signed_to_int, TestbenchIO, def_method_mock

from test.fu.functional_common import GenericFunctionalTestUnit


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams):
        fetch_layouts = gen_params.get(FetchLayouts)
        self.set_pc = TestbenchIO(Adapter(i=fetch_layouts.branch_verify_in, o=fetch_layouts.branch_verify_out))
        gen_params.get(DependencyManager).add_dependency(SetPCKey(), self.set_pc.adapter.iface)

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
def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: JumpBranchFn.Fn, xlen: int) -> Dict[str, int]:
    max_int = 2**xlen - 1
    branch_target = pc + signed_to_int(i_imm & 0x1FFF, 13)
    next_pc = 0
    res = pc + 4

    if fn == JumpBranchFn.Fn.JAL:
        next_pc = pc + signed_to_int(i_imm & 0x1FFFFF, 21)  # truncate to first 21 bits
    if fn == JumpBranchFn.Fn.JALR:
        # truncate to first 12 bits and set 0th bit to 0
        next_pc = (i1 + signed_to_int(i_imm & 0xFFF, 12)) & ~0x1
    if fn == JumpBranchFn.Fn.BEQ:
        next_pc = branch_target if i1 == i2 else pc + 4
    if fn == JumpBranchFn.Fn.BNE:
        next_pc = branch_target if i1 != i2 else pc + 4
    if fn == JumpBranchFn.Fn.BLT:
        next_pc = branch_target if signed_to_int(i1, xlen) < signed_to_int(i2, xlen) else pc + 4
    if fn == JumpBranchFn.Fn.BLTU:
        next_pc = branch_target if i1 < i2 else pc + 4
    if fn == JumpBranchFn.Fn.BGE:
        next_pc = branch_target if signed_to_int(i1, xlen) >= signed_to_int(i2, xlen) else pc + 4
    if fn == JumpBranchFn.Fn.BGEU:
        next_pc = branch_target if i1 >= i2 else pc + 4

    next_pc &= max_int
    res &= max_int

    return {"result": res, "from_pc": pc, "next_pc": next_pc}


@staticmethod
def compute_result_auipc(i1: int, i2: int, i_imm: int, pc: int, fn: JumpBranchFn.Fn, xlen: int) -> Dict[str, int]:
    max_int = 2**xlen - 1
    res = pc + 4

    if fn == JumpBranchFn.Fn.AUIPC:
        res = pc + (i_imm & 0xFFFFF000)

    res &= max_int

    return {"result": res}


ops = {
    JumpBranchFn.Fn.BEQ: {"op_type": OpType.BRANCH, "funct3": Funct3.BEQ, "funct7": 0},
    JumpBranchFn.Fn.BNE: {"op_type": OpType.BRANCH, "funct3": Funct3.BNE, "funct7": 0},
    JumpBranchFn.Fn.BLT: {"op_type": OpType.BRANCH, "funct3": Funct3.BLT, "funct7": 0},
    JumpBranchFn.Fn.BLTU: {"op_type": OpType.BRANCH, "funct3": Funct3.BLTU, "funct7": 0},
    JumpBranchFn.Fn.BGE: {"op_type": OpType.BRANCH, "funct3": Funct3.BGE, "funct7": 0},
    JumpBranchFn.Fn.BGEU: {"op_type": OpType.BRANCH, "funct3": Funct3.BGEU, "funct7": 0},
    JumpBranchFn.Fn.JAL: {"op_type": OpType.JAL, "funct3": 0, "funct7": 0},
    JumpBranchFn.Fn.JALR: {"op_type": OpType.JALR, "funct3": Funct3.JALR, "funct7": 0},
}

ops_auipc = {
    JumpBranchFn.Fn.AUIPC: {"op_type": OpType.AUIPC, "funct3": 0, "funct7": 0},
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
            JumpBranchWrapperComponent(),
            compute_result_auipc,
        ),
    ],
)
class JumpBranchUnitTest(GenericFunctionalTestUnit):
    compute_result: Callable[[int, int, int, int, Any, int], Dict[str, int]]

    def test_test(self):
        precommit_q = deque()
        # it's either this or forcing 'precommit' to exist in all FUs
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

        self.run_pipeline(
            {
                "main_proc": main_proc,
                "set_pc_mock": set_pc_mock,
            }
        )

    def __init__(self, method_name: str = "runTest"):
        super().__init__(
            self.ops,
            self.func_unit,
            self.compute_result,
            gen=GenParams(test_core_config),
            number_of_tests=300,
            seed=32323,
            zero_imm=False,
            method_name=method_name,
        )
