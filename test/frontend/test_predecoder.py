import pytest

from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit, TestbenchContext

from coreblocks.arch import CfiType, Funct3, Opcode, RasAction, Registers
from coreblocks.frontend.fetch.fetch import Predecoder
from coreblocks.params import GenParams
from coreblocks.params import configurations
from coreblocks.params.instr import BTypeInstr, ITypeInstr, JTypeInstr


def jal(rd: Registers) -> int:
    return JTypeInstr(opcode=Opcode.JAL, rd=rd, imm=0).encode()


def jalr(rd: Registers, rs1: Registers) -> int:
    return ITypeInstr(opcode=Opcode.JALR, funct3=Funct3.JALR, rd=rd, rs1=rs1, imm=0).encode()


def beq(rs1: Registers, rs2: Registers) -> int:
    return BTypeInstr(opcode=Opcode.BRANCH, funct3=Funct3.BEQ, rs1=rs1, rs2=rs2, imm=0).encode()


NOP = ITypeInstr(opcode=Opcode.OP_IMM, funct3=Funct3.ADD, rd=Registers.ZERO, rs1=Registers.ZERO, imm=0).encode()

X0, X1, X5, X6 = Registers.X0, Registers.X1, Registers.X5, Registers.X6


class TestPredecoderRasAction(TestCaseWithSimulator):
    """The cases below are the RAS hint table from the unprivileged specification"""

    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        self.gen_params = GenParams(configurations.test)
        self.m = SimpleTestCircuit(Predecoder(self.gen_params))

    @pytest.mark.parametrize(
        "instr, cfi_type, ras_action",
        [
            pytest.param(jal(X0), CfiType.JAL, RasAction.NONE, id="jal-no-link"),
            pytest.param(jal(X1), CfiType.JAL, RasAction.PUSH, id="jal-x1"),
            pytest.param(jal(X5), CfiType.JAL, RasAction.PUSH, id="jal-x5"),
            pytest.param(jal(X6), CfiType.JAL, RasAction.NONE, id="jal-non-link-rd"),
            pytest.param(jalr(X0, X6), CfiType.JALR, RasAction.NONE, id="jalr-neither"),
            pytest.param(jalr(X0, X1), CfiType.JALR, RasAction.POP, id="jalr-ret"),
            pytest.param(jalr(X0, X5), CfiType.JALR, RasAction.POP, id="jalr-ret-x5"),
            pytest.param(jalr(X1, X6), CfiType.JALR, RasAction.PUSH, id="jalr-indirect-call"),
            pytest.param(jalr(X1, X5), CfiType.JALR, RasAction.POP_AND_PUSH, id="jalr-coroutine"),
            pytest.param(jalr(X5, X1), CfiType.JALR, RasAction.POP_AND_PUSH, id="jalr-coroutine-swapped"),
            # Reading and writing one register cancels out
            pytest.param(jalr(X1, X1), CfiType.JALR, RasAction.PUSH, id="jalr-same-link-reg"),
            pytest.param(jalr(X5, X5), CfiType.JALR, RasAction.PUSH, id="jalr-same-link-reg-x5"),
            # Nothing else touches the stack
            pytest.param(beq(X1, X5), CfiType.BRANCH, RasAction.NONE, id="branch"),
            pytest.param(NOP, CfiType.INVALID, RasAction.NONE, id="nop"),
            # Compressed instructions are not predecoded at all
            pytest.param(0x8082, CfiType.INVALID, RasAction.NONE, id="compressed-ret"),
        ],
    )
    def test_ras_action(self, instr: int, cfi_type: CfiType, ras_action: RasAction):
        async def proc(sim: TestbenchContext):
            res = await self.m.predecode.call(sim, instr=instr)
            assert res["cfi_type"] == cfi_type
            assert res["ras_action"] == ras_action

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(proc)
