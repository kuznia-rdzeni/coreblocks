from amaranth import *
from typing import Dict, Callable, Any
from parameterized import parameterized_class

from coreblocks.params import *
from coreblocks.fu.jumpbranch import JumpBranchFuncUnit, JumpBranchFn, JumpComponent
from coreblocks.transactions import Method, TModule, MethodLayout
from coreblocks.transactions.core import Transaction
from coreblocks.transactions.lib import FIFO
from coreblocks.params.configurations import test_core_config
from coreblocks.params.layouts import FuncUnitLayouts, FetchLayouts
from coreblocks.utils.protocols import FuncUnit
from coreblocks.utils.utils import assign

from test.common import signed_to_int

from test.fu.functional_common import GenericFunctionalTestUnit


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

    exception = None
    if next_pc & 0b11 != 0:
        exception = ExceptionCause.INSTRUCTION_ADDRESS_MISALIGNED

    return {"result": res, "from_pc": pc, "next_pc": next_pc} | (
        {"exception": exception} if exception is not None else {}
    )


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
class JumpBranchUnitTest(GenericFunctionalTestUnit):
    compute_result: Callable[[int, int, int, int, Any, int], Dict[str, int]]
    result_layout_additional: Callable[[GenParams], MethodLayout]

    def test_test(self):
        self.run_pipeline()

    def __init__(self, method_name: str = "runTest"):
        gen_params = GenParams(test_core_config)
        super().__init__(
            self.ops,
            self.func_unit,
            self.compute_result,
            gen=gen_params,
            number_of_tests=300,
            seed=32323,
            zero_imm=False,
            method_name=method_name,
            result_layout_additional=self.result_layout_additional(gen_params),
        )
