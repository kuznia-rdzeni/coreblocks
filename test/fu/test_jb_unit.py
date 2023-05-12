from amaranth import *
from typing import Dict, Callable, Any
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn, JumpComponent
from coreblocks.transactions import Method, def_method, ModuleX
from coreblocks.params.configurations import test_core_config
from coreblocks.params.layouts import FuncUnitLayouts, FetchLayouts
from coreblocks.utils.protocols import FuncUnit

from test.common import signed_to_int

from test.fu.functional_common import GenericFunctionalTestUnit


class JumpBranchWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.jb = JumpBranchFuncUnit(GenParams(test_core_config))
        self.issue = self.jb.issue
        self.accept = Method(o=gen_params.get(FuncUnitLayouts).accept + gen_params.get(FetchLayouts).branch_verify)
        self.optypes = set()

    def elaborate(self, platform):
        m = ModuleX()

        m.submodules.jb_unit = self.jb

        @def_method(m, self.accept)
        def _(arg):
            res = self.jb.accept(m)
            br = self.jb.branch_result(m)
            return {"next_pc": br.next_pc, "result": res.result, "rob_id": res.rob_id, "rp_dst": res.rp_dst}

        return m


class JumpBranchWrapperComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return JumpBranchWrapper(gen_params)

    def get_optypes(self) -> set[OpType]:
        return JumpBranchFuncUnit.optypes


@staticmethod
def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: JumpBranchFn.Fn, xlen: int) -> Dict[str, int]:
    max_int = 2**xlen - 1
    branch_target = pc + signed_to_int(i_imm & 0xFFF, 12)
    next_pc = 0
    res = pc + 4

    if fn == JumpBranchFn.Fn.JAL:
        next_pc = pc + signed_to_int(i_imm & 0xFFFFF, 20)  # truncate to first 20 bits
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

    return {"result": res, "next_pc": next_pc}


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
            JumpComponent(),
            compute_result_auipc,
        ),
    ],
)
class JumpBranchUnitTest(GenericFunctionalTestUnit):
    compute_result: Callable[[int, int, int, int, Any, int], Dict[str, int]]

    def test_test(self):
        self.run_pipeline()

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
