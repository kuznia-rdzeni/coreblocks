import unittest
from typing import Sequence

from amaranth import *

from coreblocks.params.instr import *
from coreblocks.arch import *


class InstructionTest(unittest.TestCase):
    def do_run(self, test_cases: Sequence[tuple[RISCVInstr, int]]):
        for instr, raw_instr in test_cases:
            assert instr.encode() == raw_instr

    def test_r_type(self):
        test_cases = [
            (RTypeInstr(opcode=Opcode.OP, rd=21, funct3=Funct3.AND, rs1=10, rs2=31, funct7=Funct7.AND), 0x1F57AB3),
        ]

        self.do_run(test_cases)

    def test_i_type(self):
        test_cases = [
            (ITypeInstr(opcode=Opcode.LOAD_FP, rd=22, funct3=Funct3.D, rs1=10, imm=2047), 0x7FF53B07),
            (ITypeInstr(opcode=Opcode.LOAD_FP, rd=22, funct3=Funct3.D, rs1=10, imm=-2048), 0x80053B07),
        ]

        self.do_run(test_cases)

    def test_s_type(self):
        test_cases = [
            (STypeInstr(opcode=Opcode.STORE_FP, imm=2047, funct3=Funct3.D, rs1=31, rs2=0), 0x7E0FBFA7),
            (STypeInstr(opcode=Opcode.STORE_FP, imm=-2048, funct3=Funct3.D, rs1=5, rs2=13), 0x80D2B027),
        ]

        self.do_run(test_cases)

    def test_b_type(self):
        test_cases = [
            (BTypeInstr(opcode=Opcode.BRANCH, imm=4094, funct3=Funct3.BNE, rs1=10, rs2=0), 0x7E051FE3),
            (BTypeInstr(opcode=Opcode.BRANCH, imm=-4096, funct3=Funct3.BEQ, rs1=31, rs2=4), 0x804F8063),
        ]

        self.do_run(test_cases)

    def test_u_type(self):
        test_cases = [
            (UTypeInstr(opcode=Opcode.LUI, rd=10, imm=3102 << 12), 0xC1E537),
            (UTypeInstr(opcode=Opcode.LUI, rd=31, imm=1048575 << 12), 0xFFFFFFB7),
        ]

        self.do_run(test_cases)

    def test_j_type(self):
        test_cases = [
            (JTypeInstr(opcode=Opcode.JAL, rd=0, imm=0), 0x6F),
            (JTypeInstr(opcode=Opcode.JAL, rd=0, imm=2), 0x20006F),
            (JTypeInstr(opcode=Opcode.JAL, rd=10, imm=1048572), 0x7FDFF56F),
            (JTypeInstr(opcode=Opcode.JAL, rd=3, imm=-230), 0xF1BFF1EF),
            (JTypeInstr(opcode=Opcode.JAL, rd=15, imm=-1048576), 0x800007EF),
        ]

        self.do_run(test_cases)
