from parameterized import parameterized_class

from amaranth.sim import Settle
from amaranth import *

from coreblocks.frontend.decoder.rvc import InstrDecompress
from coreblocks.arch import *
from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from transactron.utils import ValueLike

from transactron.testing import TestCaseWithSimulator

COMMON_TESTS = [
    # Illegal instruction
    (0x0000, IllegalInstr()),
    # c.addi4spn x15, 1020
    (0x1FFC, ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.X15, funct3=Funct3.ADD, rs1=Registers.SP, imm=1020)),
    # c.lw x13, 28(x11)
    (0x4DD4, ITypeInstr(opcode=Opcode.LOAD, rd=Registers.X13, funct3=Funct3.W, rs1=Registers.X11, imm=28)),
    # c.sw x10, 20(x8)
    (0xC848, STypeInstr(opcode=Opcode.STORE, imm=20, funct3=Funct3.W, rs1=Registers.X8, rs2=Registers.X10)),
    # c.nop
    (0x0001, ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.X0, funct3=Funct3.ADD, rs1=Registers.X0, imm=0)),
    # c.addi x2, -28
    (
        0x1111,
        ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.X2, funct3=Funct3.ADD, rs1=Registers.X2, imm=-28),
    ),
    # c.li x31, -7
    (
        0x5FE5,
        ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.X31, funct3=Funct3.ADD, rs1=Registers.ZERO, imm=-7),
    ),
    # c.addi16sp 496
    (0x617D, ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.SP, funct3=Funct3.ADD, rs1=Registers.SP, imm=496)),
    # c.lui x7, -3
    (0x73F5, UTypeInstr(opcode=Opcode.LUI, rd=Registers.X7, imm=Cat(C(0, 12), C(-3, 20)))),
    # c.srli x10, 3
    (
        0x810D,
        RTypeInstr(
            opcode=Opcode.OP_IMM,
            rd=Registers.X10,
            funct3=Funct3.SR,
            rs1=Registers.X10,
            rs2=Registers.X3,
            funct7=Funct7.SL,
        ),
    ),
    # c.srai x12, 8
    (
        0x8621,
        RTypeInstr(
            opcode=Opcode.OP_IMM,
            rd=Registers.X12,
            funct3=Funct3.SR,
            rs1=Registers.X12,
            rs2=Registers.X8,
            funct7=Funct7.SA,
        ),
    ),
    # c.andi x9, 17
    (0x88C5, ITypeInstr(opcode=Opcode.OP_IMM, rd=Registers.X9, funct3=Funct3.AND, rs1=Registers.X9, imm=17)),
    # c.sub x10, x15
    (
        0x8D1D,
        RTypeInstr(
            opcode=Opcode.OP,
            rd=Registers.X10,
            funct3=Funct3.SUB,
            rs1=Registers.X10,
            rs2=Registers.X15,
            funct7=Funct7.SUB,
        ),
    ),
    # c.xor x13, x8
    (
        0x8EA1,
        RTypeInstr(
            opcode=Opcode.OP,
            rd=Registers.X13,
            funct3=Funct3.XOR,
            rs1=Registers.X13,
            rs2=Registers.X8,
            funct7=Funct7.XOR,
        ),
    ),
    # c.or x15, x14
    (
        0x8FD9,
        RTypeInstr(
            opcode=Opcode.OP,
            rd=Registers.X15,
            funct3=Funct3.OR,
            rs1=Registers.X15,
            rs2=Registers.X14,
            funct7=Funct7.OR,
        ),
    ),
    # c.and x9, x9
    (
        0x8CE5,
        RTypeInstr(
            opcode=Opcode.OP,
            rd=Registers.X9,
            funct3=Funct3.AND,
            rs1=Registers.X9,
            rs2=Registers.X9,
            funct7=Funct7.AND,
        ),
    ),
    # c.j 2012
    (0xAFF1, JTypeInstr(opcode=Opcode.JAL, rd=Registers.ZERO, imm=2012)),
    # c.beqz x8, -6
    (
        0xDC6D,
        BTypeInstr(opcode=Opcode.BRANCH, imm=-6, funct3=Funct3.BEQ, rs1=Registers.X8, rs2=Registers.ZERO),
    ),
    # c.bnez x15, 20
    (
        0xEB91,
        BTypeInstr(opcode=Opcode.BRANCH, imm=20, funct3=Funct3.BNE, rs1=Registers.X15, rs2=Registers.ZERO),
    ),
    # c.slli x13, 31
    (
        0x06FE,
        RTypeInstr(
            opcode=Opcode.OP_IMM,
            rd=Registers.X13,
            funct3=Funct3.SLL,
            rs1=Registers.X13,
            rs2=Registers.X31,
            funct7=Funct7.SL,
        ),
    ),
    # c.lwsp x2, 4
    (0x4112, ITypeInstr(opcode=Opcode.LOAD, rd=Registers.X2, funct3=Funct3.W, rs1=Registers.SP, imm=4)),
    # c.jr x30
    (
        0x8F02,
        ITypeInstr(opcode=Opcode.JALR, rd=Registers.ZERO, funct3=Funct3.JALR, rs1=Registers.X30, imm=0),
    ),
    # c.mv x2, x26
    (
        0x816A,
        RTypeInstr(
            opcode=Opcode.OP,
            rd=Registers.X2,
            funct3=Funct3.ADD,
            rs1=Registers.ZERO,
            rs2=Registers.X26,
            funct7=Funct7.ADD,
        ),
    ),
    # c.ebreak
    (0x9002, EBreakInstr()),
    # c.add x14, x8
    (
        0x9722,
        RTypeInstr(
            opcode=Opcode.OP,
            rd=Registers.X14,
            funct3=Funct3.ADD,
            rs1=Registers.X14,
            rs2=Registers.X8,
            funct7=Funct7.ADD,
        ),
    ),
    # c.swsp x31, 20
    (0xCA7E, STypeInstr(opcode=Opcode.STORE, imm=20, funct3=Funct3.W, rs1=Registers.SP, rs2=Registers.X31)),
]

RV32_TESTS = [
    # c.ld x8, 8(x9)
    (0x6480, IllegalInstr()),
    # c.sd x14, 0(x13)
    (0xE298, IllegalInstr()),
    # c.jal 40
    (0x2025, JTypeInstr(opcode=Opcode.JAL, rd=Registers.RA, imm=40)),
    # c.jal -412
    (0x3595, JTypeInstr(opcode=Opcode.JAL, rd=Registers.RA, imm=-412)),
    # c.srli x10, 32
    (0x9101, IllegalInstr()),
    # c.srai x12, 40
    (0x9621, IllegalInstr()),
    # c.subw x10, x11
    (0x9D0D, IllegalInstr()),
    # c.addw x15, x8
    (0x9FA1, IllegalInstr()),
    # c.slli x13, 63
    (0x16FE, IllegalInstr()),
]

RV64_TESTS = [
    # c.ld x8, 8(x9)
    (0x6480, ITypeInstr(opcode=Opcode.LOAD, rd=Registers.X8, funct3=Funct3.D, rs1=Registers.X9, imm=8)),
    # c.sd x14, 0(x13)
    (0xE298, STypeInstr(opcode=Opcode.STORE, imm=0, funct3=Funct3.D, rs1=Registers.X13, rs2=Registers.X14)),
    # c.addiw x13, -12,
    (
        0x36D1,
        ITypeInstr(opcode=Opcode.OP_IMM_32, rd=Registers.X13, funct3=Funct3.ADD, rs1=Registers.X13, imm=-12),
    ),
    # c.srli x10, 32
    (
        0x9101,
        RTypeInstr(
            opcode=Opcode.OP_IMM,
            rd=Registers.X10,
            funct3=Funct3.SR,
            rs1=Registers.X10,
            rs2=Registers.X0,
            funct7=Funct7.SL | 1,
        ),
    ),
    # c.srai x12, 40
    (
        0x9621,
        RTypeInstr(
            opcode=Opcode.OP_IMM,
            rd=Registers.X12,
            funct3=Funct3.SR,
            rs1=Registers.X12,
            rs2=Registers.X8,
            funct7=Funct7.SA | 1,
        ),
    ),
    # c.subw x10, x11
    (
        0x9D0D,
        RTypeInstr(
            opcode=Opcode.OP32,
            rd=Registers.X10,
            funct3=Funct3.SUB,
            rs1=Registers.X10,
            rs2=Registers.X11,
            funct7=Funct3.SUB,
        ),
    ),
    # c.addw x15, x8
    (
        0x9FA1,
        RTypeInstr(
            opcode=Opcode.OP32,
            rd=Registers.X15,
            funct3=Funct3.ADD,
            rs1=Registers.X15,
            rs2=Registers.X8,
            funct7=Funct3.ADD,
        ),
    ),
    # c.slli x13, 63
    (
        0x16FE,
        RTypeInstr(
            opcode=Opcode.OP_IMM,
            rd=Registers.X13,
            funct3=Funct3.SLL,
            rs1=Registers.X13,
            rs2=Registers.X31,
            funct7=Funct7.SL | 1,
        ),
    ),
    # c.ldsp x29, 40
    (0x7EA2, ITypeInstr(opcode=Opcode.LOAD, rd=Registers.X29, funct3=Funct3.D, rs1=Registers.SP, imm=40)),
    # c.sdsp x4, 8
    (0xE412, STypeInstr(opcode=Opcode.STORE, imm=8, funct3=Funct3.D, rs1=Registers.SP, rs2=Registers.X4)),
]


@parameterized_class(
    ("name", "isa_xlen", "test_cases"),
    [("rv32ic", 32, COMMON_TESTS + RV32_TESTS), ("rv64ic", 64, COMMON_TESTS + RV64_TESTS)],
)
class TestInstrDecompress(TestCaseWithSimulator):
    isa_xlen: int
    test_cases: list[tuple[int, ValueLike]]

    def test(self):
        self.gen_params = GenParams(
            test_core_config.replace(compressed=True, xlen=self.isa_xlen, fetch_block_bytes_log=3)
        )
        self.m = InstrDecompress(self.gen_params)

        def process():
            for instr_in, instr_out in self.test_cases:
                yield self.m.instr_in.eq(instr_in)
                expected = Signal(32)
                yield expected.eq(instr_out)
                yield Settle()

                assert (yield self.m.instr_out) == (yield expected)
                yield

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(process)
