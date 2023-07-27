from amaranth.sim import *

from ..common import TestCaseWithSimulator

from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.frontend.decoder import InstrDecoder, Encoding, _instructions_by_optype
from unittest import TestCase
from typing import Optional


class TestDecoder(TestCaseWithSimulator):
    class InstrTest:
        def __init__(
            self,
            encoding,
            opcode,
            funct3=None,
            funct7=None,
            funct12=None,
            rd=None,
            rd_rf=RegisterType.X,
            rs1=None,
            rs1_rf=RegisterType.X,
            rs2=None,
            rs2_rf=RegisterType.X,
            imm=None,
            succ=None,
            pred=None,
            fm=None,
            imm2=None,
            op=None,
            illegal=0,
        ):
            self.encoding = encoding
            self.opcode = opcode
            self.funct3 = funct3
            self.funct7 = funct7
            self.funct12 = funct12
            self.rd = rd
            self.rd_rf = rd_rf
            self.rs1 = rs1
            self.rs1_rf = rs1_rf
            self.rs2 = rs2
            self.rs2_rf = rs2_rf
            self.imm = imm
            self.succ = succ
            self.pred = pred
            self.fm = fm
            self.imm2 = imm2
            self.op = op
            self.illegal = illegal

    DECODER_TESTS_I = [
        # Arithmetic
        InstrTest(0x02A28213, Opcode.OP_IMM, Funct3.ADD, rd=4, rs1=5, imm=42, op=OpType.ARITHMETIC),
        InstrTest(0x003100B3, Opcode.OP, Funct3.ADD, Funct7.ADD, rd=1, rs1=2, rs2=3, op=OpType.ARITHMETIC),
        InstrTest(0x40418133, Opcode.OP, Funct3.ADD, Funct7.SUB, rd=2, rs1=3, rs2=4, op=OpType.ARITHMETIC),
        InstrTest(0x001230B7, Opcode.OP_IMM, Funct3.ADD, rd=1, rs1=0, imm=0x123 << 12, op=OpType.ARITHMETIC),
        # Compare
        InstrTest(0x07BF2A13, Opcode.OP_IMM, Funct3.SLT, rd=20, rs1=30, imm=123, op=OpType.COMPARE),
        InstrTest(0x0FFFBA93, Opcode.OP_IMM, Funct3.SLTU, rd=21, rs1=31, imm=0xFF, op=OpType.COMPARE),
        InstrTest(0x00C5A533, Opcode.OP, Funct3.SLT, Funct7.SLT, rd=10, rs1=11, rs2=12, op=OpType.COMPARE),
        InstrTest(0x00C5B533, Opcode.OP, Funct3.SLTU, Funct7.SLT, rd=10, rs1=11, rs2=12, op=OpType.COMPARE),
        # Logic
        InstrTest(0xFFF04013, Opcode.OP_IMM, Funct3.XOR, rd=0, rs1=0, imm=-1, op=OpType.LOGIC),
        InstrTest(0x3FF0E093, Opcode.OP_IMM, Funct3.OR, rd=1, rs1=1, imm=0x3FF, op=OpType.LOGIC),
        InstrTest(0x000FFF13, Opcode.OP_IMM, Funct3.AND, rd=30, rs1=31, imm=0, op=OpType.LOGIC),
        InstrTest(0x003140B3, Opcode.OP, Funct3.XOR, Funct7.XOR, rd=1, rs1=2, rs2=3, op=OpType.LOGIC),
        InstrTest(0x003160B3, Opcode.OP, Funct3.OR, Funct7.OR, rd=1, rs1=2, rs2=3, op=OpType.LOGIC),
        InstrTest(0x003170B3, Opcode.OP, Funct3.AND, Funct7.AND, rd=1, rs1=2, rs2=3, op=OpType.LOGIC),
        # Shift
        InstrTest(0x00029793, Opcode.OP_IMM, Funct3.SLL, Funct7.SL, rd=15, rs1=5, imm=0, op=OpType.SHIFT),
        InstrTest(0x00F2D793, Opcode.OP_IMM, Funct3.SR, Funct7.SL, rd=15, rs1=5, imm=15, op=OpType.SHIFT),
        InstrTest(0x41F2D793, Opcode.OP_IMM, Funct3.SR, Funct7.SA, rd=15, rs1=5, imm=31, op=OpType.SHIFT),
        InstrTest(0x019297B3, Opcode.OP, Funct3.SLL, Funct7.SL, rd=15, rs1=5, rs2=25, op=OpType.SHIFT),
        InstrTest(0x0192D7B3, Opcode.OP, Funct3.SR, Funct7.SL, rd=15, rs1=5, rs2=25, op=OpType.SHIFT),
        InstrTest(0x4192D7B3, Opcode.OP, Funct3.SR, Funct7.SA, rd=15, rs1=5, rs2=25, op=OpType.SHIFT),
        # AUIPC
        InstrTest(0x00777F17, Opcode.AUIPC, rd=30, imm=0x777 << 12, op=OpType.AUIPC),
        # Jumps
        InstrTest(0x000000EF, Opcode.JAL, rd=1, imm=0, op=OpType.JAL),
        InstrTest(0xFFE100E7, Opcode.JALR, Funct3.JALR, rd=1, rs1=2, imm=-2, op=OpType.JALR),
        # Branch
        InstrTest(0x00209463, Opcode.BRANCH, Funct3.BNE, rs1=1, rs2=2, imm=4 << 1, op=OpType.BRANCH),
        InstrTest(0x00310463, Opcode.BRANCH, Funct3.BEQ, rs1=2, rs2=3, imm=4 << 1, op=OpType.BRANCH),
        InstrTest(0x0041D463, Opcode.BRANCH, Funct3.BGE, rs1=3, rs2=4, imm=4 << 1, op=OpType.BRANCH),
        InstrTest(0x00524463, Opcode.BRANCH, Funct3.BLT, rs1=4, rs2=5, imm=4 << 1, op=OpType.BRANCH),
        InstrTest(0x0062F463, Opcode.BRANCH, Funct3.BGEU, rs1=5, rs2=6, imm=4 << 1, op=OpType.BRANCH),
        InstrTest(0x00736463, Opcode.BRANCH, Funct3.BLTU, rs1=6, rs2=7, imm=4 << 1, op=OpType.BRANCH),
        # Load
        InstrTest(0x00B48403, Opcode.LOAD, Funct3.B, rd=8, rs1=9, imm=11, op=OpType.LOAD),
        InstrTest(0x00C54483, Opcode.LOAD, Funct3.BU, rd=9, rs1=10, imm=12, op=OpType.LOAD),
        InstrTest(0x00D59503, Opcode.LOAD, Funct3.H, rd=10, rs1=11, imm=13, op=OpType.LOAD),
        InstrTest(0x00E65583, Opcode.LOAD, Funct3.HU, rd=11, rs1=12, imm=14, op=OpType.LOAD),
        InstrTest(0x00F6A603, Opcode.LOAD, Funct3.W, rd=12, rs1=13, imm=15, op=OpType.LOAD),
        InstrTest(0xFFA09703, Opcode.LOAD, Funct3.H, rd=14, rs1=1, imm=-6, op=OpType.LOAD),
        # Store
        InstrTest(0x00D70823, Opcode.STORE, Funct3.B, rs1=14, rs2=13, imm=16, op=OpType.STORE),
        InstrTest(0x00E798A3, Opcode.STORE, Funct3.H, rs1=15, rs2=14, imm=17, op=OpType.STORE),
        InstrTest(0x00F82923, Opcode.STORE, Funct3.W, rs1=16, rs2=15, imm=18, op=OpType.STORE),
        # Fence
        InstrTest(
            0x0320000F,
            Opcode.MISC_MEM,
            Funct3.FENCE,
            rd=0,
            rs1=0,
            succ=FenceTarget.MEM_R,
            pred=(FenceTarget.MEM_R | FenceTarget.MEM_W),
            fm=FenceFm.NONE,
            op=OpType.FENCE,
        ),
        # ECALL
        InstrTest(0x00000073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.ECALL, op=OpType.ECALL),
        # EBREAK
        InstrTest(0x00100073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.EBREAK, op=OpType.EBREAK),
    ]
    DECODER_TESTS_ZIFENCEI = [
        InstrTest(0x0000100F, Opcode.MISC_MEM, Funct3.FENCEI, rd=0, rs1=0, imm=0, op=OpType.FENCEI),
    ]
    DECODER_TESTS_ZICSR = [
        InstrTest(0x001A9A73, Opcode.SYSTEM, Funct3.CSRRW, rd=20, rs1=21, imm2=0x01, op=OpType.CSR_REG),
        InstrTest(0x002B2AF3, Opcode.SYSTEM, Funct3.CSRRS, rd=21, rs1=22, imm2=0x02, op=OpType.CSR_REG),
        InstrTest(0x004BBB73, Opcode.SYSTEM, Funct3.CSRRC, rd=22, rs1=23, imm2=0x04, op=OpType.CSR_REG),
        InstrTest(0x001FDA73, Opcode.SYSTEM, Funct3.CSRRWI, rd=20, imm=0x1F, imm2=0x01, op=OpType.CSR_IMM),
        InstrTest(0x0027EAF3, Opcode.SYSTEM, Funct3.CSRRSI, rd=21, imm=0xF, imm2=0x02, op=OpType.CSR_IMM),
        InstrTest(0x00407B73, Opcode.SYSTEM, Funct3.CSRRCI, rd=22, imm=0x0, imm2=0x04, op=OpType.CSR_IMM),
    ]
    DECODER_TESTS_ILLEGAL = [
        InstrTest(0xFFFFFFFF, Opcode.OP_IMM, illegal=1),
        InstrTest(0x003160FF, Opcode.OP, Funct3.OR, Funct7.OR, rd=1, rs1=2, rs2=3, op=OpType.LOGIC, illegal=1),
        InstrTest(0x000000F3, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.ECALL, op=OpType.ECALL, illegal=1),
    ]
    DECODER_TESTS_M = [
        InstrTest(0x02310133, Opcode.OP, Funct3.MUL, Funct7.MULDIV, rd=2, rs1=2, rs2=3, op=OpType.MUL),
        InstrTest(0x02341133, Opcode.OP, Funct3.MULH, Funct7.MULDIV, rd=2, rs1=8, rs2=3, op=OpType.MUL),
        InstrTest(0x02A12233, Opcode.OP, Funct3.MULHSU, Funct7.MULDIV, rd=4, rs1=2, rs2=10, op=OpType.MUL),
        InstrTest(0x02A43233, Opcode.OP, Funct3.MULHU, Funct7.MULDIV, rd=4, rs1=8, rs2=10, op=OpType.MUL),
        InstrTest(0x02314133, Opcode.OP, Funct3.DIV, Funct7.MULDIV, rd=2, rs1=2, rs2=3, op=OpType.DIV_REM),
        InstrTest(0x02745133, Opcode.OP, Funct3.DIVU, Funct7.MULDIV, rd=2, rs1=8, rs2=7, op=OpType.DIV_REM),
        InstrTest(0x02716233, Opcode.OP, Funct3.REM, Funct7.MULDIV, rd=4, rs1=2, rs2=7, op=OpType.DIV_REM),
        InstrTest(0x02A47233, Opcode.OP, Funct3.REMU, Funct7.MULDIV, rd=4, rs1=8, rs2=10, op=OpType.DIV_REM),
    ]
    DECODER_TESTS_XINTMACHINEMODE = [
        # MRET
        InstrTest(0x30200073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.MRET, op=OpType.MRET),
        # WFI
        InstrTest(0x10500073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.WFI, op=OpType.WFI),
    ]
    DECODER_TESTS_XINTSUPERVISOR = [
        # SRET
        InstrTest(0x10200073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.SRET, op=OpType.SRET),
        # SFENCE.VMA
        InstrTest(0x12208073, Opcode.SYSTEM, Funct3.PRIV, Funct7.SFENCEVMA, rs1=1, rs2=2, op=OpType.SFENCEVMA),
    ]
    DECODER_TESTS_ZBB = [
        InstrTest(
            0x60201013,
            Opcode.OP_IMM,
            Funct3.CPOP,
            funct12=Funct12.CPOP,
            rd=0,
            rs1=0,
            op=OpType.UNARY_BIT_MANIPULATION_5,
        ),
        InstrTest(0x40007033, Opcode.OP, Funct3.ANDN, Funct7.ANDN, rd=0, rs1=0, rs2=0, op=OpType.BIT_MANIPULATION),
        InstrTest(
            0x60411093,
            Opcode.OP_IMM,
            Funct3.SEXTB,
            funct12=Funct12.SEXTB,
            rd=1,
            rs1=2,
            op=OpType.UNARY_BIT_MANIPULATION_1,
        ),
    ]
    DECODER_TESTS_V_INTEGERS = [
        InstrTest(
            0x022180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VADD * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vadd.vv v1, v2, v3
        InstrTest(
            0x002180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VADD * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vadd.vv v1, v2, v3, v0.t
        InstrTest(
            0x0245B057,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VADD * 2 + 1,
            rd_rf=RegisterType.V,
            rd=0,
            rs2_rf=RegisterType.V,
            rs2=4,
            imm=11,
            op=OpType.V_ARITHMETIC,
        ),  # vadd.vi v0, v4, 11
        InstrTest(
            0x0283CFD7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VADD * 2 + 1,
            rd_rf=RegisterType.V,
            rd=31,
            rs2_rf=RegisterType.V,
            rs2=8,
            rs1_rf=RegisterType.X,
            rs1=7,
            op=OpType.V_ARITHMETIC,
        ),  # vadd.vx v31, v8, x7
        InstrTest(
            0x0083CFD7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VADD * 2,
            rd_rf=RegisterType.V,
            rd=31,
            rs2_rf=RegisterType.V,
            rs2=8,
            rs1_rf=RegisterType.X,
            rs1=7,
            op=OpType.V_ARITHMETIC,
        ),  # vadd.vx v31, v8, x7, v0.t
        InstrTest(
            0x0A818257,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSUB * 2 + 1,
            rd_rf=RegisterType.V,
            rd=4,
            rs2_rf=RegisterType.V,
            rs2=8,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsub.vv v4, v8, v3
        InstrTest(
            0x0A30C157,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSUB * 2 + 1,
            rd_rf=RegisterType.V,
            rd=2,
            rs2_rf=RegisterType.V,
            rs2=3,
            rs1_rf=RegisterType.X,
            rs1=1,
            op=OpType.V_ARITHMETIC,
        ),  # vsub.vx v2, v3, x1
        InstrTest(
            0x0E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VRSUB * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vrsub.vx v1, v2, x3
        InstrTest(
            0x0E23B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VRSUB * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=7,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vrsub.vi v1, v2, 7
        InstrTest(
            0x122180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMINU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vminu.vv v1, v2, v3
        InstrTest(
            0x1221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMINU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vminu.vx v1, v2, x3
        InstrTest(
            0x162180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMIN * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmin.vv v1, v2, v3
        InstrTest(
            0x1621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMIN * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmin.vx v1, v2, x3
        InstrTest(
            0x1A2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMAXU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmaxu.vv v1, v2, v3
        InstrTest(
            0x1A21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMAXU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmaxu.vx v1, v2, x3
        InstrTest(
            0x1E2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMAX * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmax.vv v1, v2, v3
        InstrTest(
            0x1E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMAX * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmax.vx v1, v2, x3
        InstrTest(
            0x262180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VAND * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vand.vv v1, v2, v3
        InstrTest(
            0x2621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VAND * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vand.vx v1, v2, x3
        InstrTest(
            0x2627B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VAND * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=15,
            op=OpType.V_ARITHMETIC,
        ),  # vand.vi v1, v2, 15
        InstrTest(
            0x2A2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VOR * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vor.vv v1, v2, v3
        InstrTest(
            0x2A21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VOR * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vor.vx v1, v2, x3
        InstrTest(
            0x2A2830D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VOR * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=-16,
            op=OpType.V_ARITHMETIC,
        ),  # vor.vi v1, v2, -16
        InstrTest(
            0x2E2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VXOR * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vxor.vv v1, v2, v3
        InstrTest(
            0x2E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VXOR * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vxor.vx v1, v2, x3
        InstrTest(
            0x2E2030D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VXOR * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=0,
            op=OpType.V_ARITHMETIC,
        ),  # vxor.vi v1, v2, 0
        InstrTest(
            0x322180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VRGATHER * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vrgather.vv v1, v2, v3
        InstrTest(
            0x3221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VRGATHER * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vrgather.vx v1, v2, x3
        InstrTest(
            0x322230D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VRGATHER * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=4,
            op=OpType.V_PERMUTATION,
        ),  # vrgather.vi v1, v2, 4
        InstrTest(
            0x3A21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSLIDEUP * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vslideup.vx v1, v2, x3
        InstrTest(
            0x3A2130D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSLIDEUP * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=2,
            op=OpType.V_PERMUTATION,
        ),  # vslideup.vi v1, v2, 2
        InstrTest(
            0x3A2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VRGATHEREI16 * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vrgatherei16.vv v1, v2, v3
        InstrTest(
            0x3E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSLIDEDOWN * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vslidedown.vx v1, v2, x3
        InstrTest(
            0x3E2130D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSLIDEDOWN * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=2,
            op=OpType.V_PERMUTATION,
        ),  # vslidedown.vi v1, v2, 2
        InstrTest(
            0x402180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VADC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vadc.vvm v1, v2, v3, v0
        InstrTest(
            0x4021C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VADC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vadc.vxm v1, v2, x3, v0
        InstrTest(
            0x4021B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VADC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vadc.vim v1, v2, 3, v0
        InstrTest(
            0x442180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMADC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vmadc.vvm v1, v2, v3, v0
        InstrTest(
            0x4421C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMADC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vmadc.vxm v1, v2, x3, v0
        InstrTest(
            0x4421B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMADC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vmadc.vim v1, v2, 3, v0
        InstrTest(
            0x482180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSBC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsbc.vvm v1, v2, v3, v0
        InstrTest(
            0x4821C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSBC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsbc.vxm v1, v2, x3, v0
        InstrTest(
            0x4C2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSBC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vmsbc.vvm v1, v2, v3, v0
        InstrTest(
            0x4C21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSBC * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vmsbc.vxm v1, v2, x3, v0
        InstrTest(
            0x5C2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMERGE * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vmerge.vvm v1, v2, v3, v0
        InstrTest(
            0x5C21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMERGE * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vmerge.vxm v1, v2, x3, v0
        InstrTest(
            0x5C21B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMERGE * 2,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_PERMUTATION,
        ),  # vmerge.vim v1, v2, 3, v0
        InstrTest(
            0x5E0180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMV * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=0,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vmv.v.v v1, v3
        InstrTest(
            0x5E01C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMV * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=0,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_PERMUTATION,
        ),  # vmv.v.x v1, x3
        InstrTest(
            0x5E01B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMV * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=0,
            imm=3,
            op=OpType.V_PERMUTATION,
        ),  # vmv.v.i v1, 3
        InstrTest(
            0x622180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSEQ * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmseq.vv v1, v2, v3
        InstrTest(
            0x6221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSEQ * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmseq.vx v1, v2, x3
        InstrTest(
            0x6221B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMSEQ * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmseq.vi v1, v2, 3
        InstrTest(
            0x662180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSNE * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsne.vv v1, v2, v3
        InstrTest(
            0x6621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSNE * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsne.vx v1, v2, x3
        InstrTest(
            0x6621B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMSNE * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsne.vi v1, v2, 3
        InstrTest(
            0x6A2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSLTU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsltu.vv v1, v2, v3
        InstrTest(
            0x6A21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSLTU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsltu.vx v1, v2, x3
        InstrTest(
            0x6E2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSLT * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmslt.vv v1, v2, v3
        InstrTest(
            0x6E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSLT * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmslt.vx v1, v2, x3
        InstrTest(
            0x722180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSLEU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsleu.vv v1, v2, v3
        InstrTest(
            0x7221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSLEU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsleu.vx v1, v2, x3
        InstrTest(
            0x7221B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMSLEU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsleu.vi v1, v2, 3
        InstrTest(
            0x762180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VMSLE * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsle.vv v1, v2, v3
        InstrTest(
            0x7621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSLE * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsle.vx v1, v2, x3
        InstrTest(
            0x7621B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMSLE * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsle.vi v1, v2, 3
        InstrTest(
            0x7A21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSGTU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsgtu.vx v1, v2, x3
        InstrTest(
            0x7A21B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMSGTU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsgtu.vi v1, v2, 3
        InstrTest(
            0x7E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VMSGT * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsgt.vx v1, v2, x3
        InstrTest(
            0x7E21B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMSGT * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vmsgt.vi v1, v2, 3
        InstrTest(
            0x822180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSADDU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsaddu.vv v1, v2, v3
        InstrTest(
            0x8221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSADDU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsaddu.vx v1, v2, x3
        InstrTest(
            0x8221B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSADDU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsaddu.vi v1, v2, 3
        InstrTest(
            0x862180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSADD * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsadd.vv v1, v2, v3
        InstrTest(
            0x8621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSADD * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsadd.vx v1, v2, x3
        InstrTest(
            0x8621B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSADD * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsadd.vi v1, v2, 3
        InstrTest(
            0x8A2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSSUBU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vssubu.vv v1, v2, v3
        InstrTest(
            0x8A21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSSUBU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vssubu.vx v1, v2, x3
        InstrTest(
            0x8E2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSSUB * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vssub.vv v1, v2, v3
        InstrTest(
            0x8E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSSUB * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vssub.vx v1, v2, x3
        InstrTest(
            0x962180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSLL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsll.vv v1, v2, v3
        InstrTest(
            0x9621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSLL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsll.vx v1, v2, x3
        InstrTest(
            0x9621B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSLL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsll.vi v1, v2, 3
        InstrTest(
            0x9E2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSMUL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsmul.vv v1, v2, v3
        InstrTest(
            0x9E21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSMUL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NOT_IMPLEMENTED,
        ),  # vsmul.vx v1, v2, x3
        InstrTest(
            0x9E803057,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMV1R * 2 + 1,
            rd_rf=RegisterType.V,
            rd=0,
            rs2_rf=RegisterType.V,
            rs2=8,
            imm=0,
            op=OpType.V_PERMUTATION,
        ),  # vmv1r.v v0, v8
        InstrTest(
            0x9E80B057,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMV2R * 2 + 1,
            rd_rf=RegisterType.V,
            rd=0,
            rs2_rf=RegisterType.V,
            rs2=8,
            imm=1,
            op=OpType.V_PERMUTATION,
        ),  # vmv2r.v v0, v8
        InstrTest(
            0x9E81B057,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMV4R * 2 + 1,
            rd_rf=RegisterType.V,
            rd=0,
            rs2_rf=RegisterType.V,
            rs2=8,
            imm=3,
            op=OpType.V_PERMUTATION,
        ),  # vmv4r.v v0, v8
        InstrTest(
            0x9E83B057,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VMV8R * 2 + 1,
            rd_rf=RegisterType.V,
            rd=0,
            rs2_rf=RegisterType.V,
            rs2=8,
            imm=7,
            op=OpType.V_PERMUTATION,
        ),  # vmv8r.v v0, v8
        InstrTest(
            0xA22180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSRL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsrl.vv v1, v2, v3
        InstrTest(
            0xA221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSRL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsrl.vx v1, v2, x3
        InstrTest(
            0xA221B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSRL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsrl.vi v1, v2, 3
        InstrTest(
            0xA62180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VSRA * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsra.vv v1, v2, v3
        InstrTest(
            0xA621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VSRA * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsra.vx v1, v2, x3
        InstrTest(
            0xA621B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VSRA * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC,
        ),  # vsra.vi v1, v2, 3
        InstrTest(
            0xB22180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VNSRL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnsrl.wv v1, v2, v3
        InstrTest(
            0xB221C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VNSRL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnsrl.wx v1, v2, x3
        InstrTest(
            0xB221B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VNSRL * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnsrl.wi v1, v2, 3
        InstrTest(
            0xB62180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VNSRA * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnsra.wv v1, v2, v3
        InstrTest(
            0xB621C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VNSRA * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnsra.wx v1, v2, x3
        InstrTest(
            0xB621B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VNSRA * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnsra.wi v1, v2, 3
        InstrTest(
            0xBA2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VNCLIPU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnclipu.wv v1, v2, v3
        InstrTest(
            0xBA21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VNCLIPU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnclipu.wx v1, v2, x3
        InstrTest(
            0xBA21B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VNCLIPU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnclipu.wi v1, v2, 3
        InstrTest(
            0xBE2180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VNCLIP * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnclip.wv v1, v2, v3
        InstrTest(
            0xBE21C0D7,
            Opcode.OP_V,
            Funct3.OPIVX,
            Funct6.VNCLIP * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.X,
            rs1=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnclip.wx v1, v2, x3
        InstrTest(
            0xBE21B0D7,
            Opcode.OP_V,
            Funct3.OPIVI,
            Funct6.VNCLIP * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            imm=3,
            op=OpType.V_ARITHMETIC_NARROWING,
        ),  # vnclip.wi v1, v2, 3
        InstrTest(
            0xC22180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VWREDSUMU * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_REDUCTION,
        ),  # vwredsumu.vs v1, v2, v3
        InstrTest(
            0xC62180D7,
            Opcode.OP_V,
            Funct3.OPIVV,
            Funct6.VWREDSUM * 2 + 1,
            rd_rf=RegisterType.V,
            rd=1,
            rs2_rf=RegisterType.V,
            rs2=2,
            rs1_rf=RegisterType.V,
            rs1=3,
            op=OpType.V_REDUCTION,
        ),  # vwredsum.vs v1, v2, v3
    ]
    DECODER_TESTS_V_CONTROL = [
        InstrTest(0x8020F057, Opcode.OP_V, Funct3.OPCFG, rd=0, rs1=1, rs2=2, op=OpType.V_CONTROL),  # vsetvl x0, x1, x2
        InstrTest(
            0x0D307057, Opcode.OP_V, Funct3.OPCFG, rd=0, rs1=0, imm2=0b11010011, op=OpType.V_CONTROL
        ),  # vsetvli x0, x0, e32,m8,ta,ma
        InstrTest(
            0xCD3470D7, Opcode.OP_V, Funct3.OPCFG, rd=1, imm=8, imm2=0b110011010011, op=OpType.V_CONTROL
        ),  # vsetivli x1, 8, e32,m8,ta,ma
    ]

    DECODER_TESTS_V_MEMORY = [
        InstrTest(
            0x02008187,
            Opcode.LOAD_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_LOAD,
        ),  # vle8.v v3, (x1)
        InstrTest(
            0x0200D187,
            Opcode.LOAD_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_LOAD,
        ),  # vle16.v v3, (x1)
        InstrTest(
            0x0200E187,
            Opcode.LOAD_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_LOAD,
        ),  # vle32.v v3, (x1)
        InstrTest(
            0x0200F187,
            Opcode.LOAD_FP,
            Funct3.VMEM64,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_LOAD,
        ),  # vle64.v v3, (x1)
        InstrTest(
            0x02B08187,
            Opcode.LOAD_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x02B,
            op=OpType.V_LOAD,
        ),  # vlm.v v3, (x1)
        InstrTest(
            0x0A208187,
            Opcode.LOAD_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_LOAD,
        ),  # vlse8.v v3, (x1), x2
        InstrTest(
            0x0A20D187,
            Opcode.LOAD_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_LOAD,
        ),  # vlse16.v v3, (x1), x2
        InstrTest(
            0x0A20E187,
            Opcode.LOAD_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_LOAD,
        ),  # vlse32.v v3, (x1), x2
        InstrTest(
            0x0A20F187,
            Opcode.LOAD_FP,
            Funct3.VMEM64,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_LOAD,
        ),  # vlse64.v v3, (x1), x2
        InstrTest(
            0x06208187,
            Opcode.LOAD_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x062,
            op=OpType.V_LOAD,
        ),  # vluxei8.v v3, (x1), v2
        InstrTest(
            0x0620D187,
            Opcode.LOAD_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x062,
            op=OpType.V_LOAD,
        ),  # vluxei16.v v3, (x1), v2
        InstrTest(
            0x0620E187,
            Opcode.LOAD_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x062,
            op=OpType.V_LOAD,
        ),  # vluxei32.v v3, (x1), v2
        InstrTest(
            0x0E208187,
            Opcode.LOAD_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x0E2,
            op=OpType.V_LOAD,
        ),  # vloxei8.v v3, (x1), v2
        InstrTest(
            0x0E20D187,
            Opcode.LOAD_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x0E2,
            op=OpType.V_LOAD,
        ),  # vloxei16.v v3, (x1), v2
        InstrTest(
            0x0E20E187,
            Opcode.LOAD_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x0E2,
            op=OpType.V_LOAD,
        ),  # vloxei32.v v3, (x1), v2
        InstrTest(
            0x020081A7,
            Opcode.STORE_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_STORE,
        ),  # vse8.v v3, (x1)
        InstrTest(
            0x0200D1A7,
            Opcode.STORE_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_STORE,
        ),  # vse16.v v3, (x1)
        InstrTest(
            0x0200E1A7,
            Opcode.STORE_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_STORE,
        ),  # vse32.v v3, (x1)
        InstrTest(
            0x0200F1A7,
            Opcode.STORE_FP,
            Funct3.VMEM64,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x020,
            op=OpType.V_STORE,
        ),  # vse64.v v3, (x1)
        InstrTest(
            0x02B081A7,
            Opcode.STORE_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            imm2=0x02B,
            op=OpType.V_STORE,
        ),  # vsm.v v3, (x1)
        InstrTest(
            0x0A2081A7,
            Opcode.STORE_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_STORE,
        ),  # vsse8.v v3, (x1), x2
        InstrTest(
            0x0A20D1A7,
            Opcode.STORE_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_STORE,
        ),  # vsse16.v v3, (x1), x2
        InstrTest(
            0x0A20E1A7,
            Opcode.STORE_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_STORE,
        ),  # vsse32.v v3, (x1), x2
        InstrTest(
            0x0A20F1A7,
            Opcode.STORE_FP,
            Funct3.VMEM64,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.X,
            imm2=0x0A2,
            op=OpType.V_STORE,
        ),  # vsse64.v v3, (x1), x2
        InstrTest(
            0x062081A7,
            Opcode.STORE_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x062,
            op=OpType.V_STORE,
        ),  # vsuxei8.v v3, (x1), v2
        InstrTest(
            0x0620D1A7,
            Opcode.STORE_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x062,
            op=OpType.V_STORE,
        ),  # vsuxei16.v v3, (x1), v2
        InstrTest(
            0x0620E1A7,
            Opcode.STORE_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x062,
            op=OpType.V_STORE,
        ),  # vsuxei32.v v3, (x1), v2
        InstrTest(
            0x0E2081A7,
            Opcode.STORE_FP,
            Funct3.VMEM8,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x0E2,
            op=OpType.V_STORE,
        ),  # vsoxei8.v v3, (x1), v2
        InstrTest(
            0x0E20D1A7,
            Opcode.STORE_FP,
            Funct3.VMEM16,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x0E2,
            op=OpType.V_STORE,
        ),  # vsoxei16.v v3, (x1), v2
        InstrTest(
            0x0E20E1A7,
            Opcode.STORE_FP,
            Funct3.VMEM32,
            rd=3,
            rd_rf=RegisterType.V,
            rs1=1,
            rs1_rf=RegisterType.X,
            rs2=2,
            rs2_rf=RegisterType.V,
            imm2=0x0E2,
            op=OpType.V_STORE,
        ),  # vsoxei32.v v3, (x1), v2
    ]

    def setUp(self):
        gen = GenParams(
            test_core_config.replace(
                _implied_extensions=Extension.G
                | Extension.XINTMACHINEMODE
                | Extension.XINTSUPERVISOR
                | Extension.ZBB
                | Extension.V
            )
        )
        self.decoder = InstrDecoder(gen)
        self.cnt = 1

    def do_test(self, test):
        def process():
            yield self.decoder.instr.eq(test.encoding)
            yield Settle()
            # For pprint in gtkwave
            yield Delay(1e-7)

            self.assertEqual((yield self.decoder.illegal), test.illegal)
            if test.illegal:
                return

            self.assertEqual((yield self.decoder.opcode), test.opcode)

            if test.funct3 is not None:
                self.assertEqual((yield self.decoder.funct3), test.funct3)
            self.assertEqual((yield self.decoder.funct3_v), test.funct3 is not None)

            if test.funct7 is not None:
                self.assertEqual((yield self.decoder.funct7), test.funct7)
            self.assertEqual((yield self.decoder.funct7_v), test.funct7 is not None)

            if test.funct12 is not None:
                self.assertEqual((yield self.decoder.funct12), test.funct12)
            self.assertEqual((yield self.decoder.funct12_v), test.funct12 is not None)

            if test.rd is not None:
                self.assertEqual((yield self.decoder.rd), test.rd)
                self.assertEqual((yield self.decoder.rd_type), test.rd_rf)
            self.assertEqual((yield self.decoder.rd_v), test.rd is not None)

            if test.rs1 is not None:
                self.assertEqual((yield self.decoder.rs1), test.rs1)
                self.assertEqual((yield self.decoder.rs1_type), test.rs1_rf)
            self.assertEqual((yield self.decoder.rs1_v), test.rs1 is not None)

            if test.rs2 is not None:
                self.assertEqual((yield self.decoder.rs2), test.rs2)
                self.assertEqual((yield self.decoder.rs2_type), test.rs2_rf)
            self.assertEqual((yield self.decoder.rs2_v), test.rs2 is not None)

            if test.imm is not None:
                self.assertEqual((yield self.decoder.imm.as_signed()), test.imm)

            if test.succ is not None:
                self.assertEqual((yield self.decoder.succ), test.succ)

            if test.pred is not None:
                self.assertEqual((yield self.decoder.pred), test.pred)

            if test.fm is not None:
                self.assertEqual((yield self.decoder.fm), test.fm)

            if test.imm2 is not None:
                self.assertEqual((yield self.decoder.imm2), test.imm2)

            self.assertEqual((yield self.decoder.optype), test.op, f"funct3: {test.funct3}, funct7: {test.funct7}")

        with self.run_simulation(self.decoder) as sim:
            sim.add_process(process)

    def test_i(self):
        for test in self.DECODER_TESTS_I:
            self.do_test(test)

    def test_zifencei(self):
        for test in self.DECODER_TESTS_ZIFENCEI:
            self.do_test(test)

    def test_zicsr(self):
        for test in self.DECODER_TESTS_ZICSR:
            self.do_test(test)

    def test_m(self):
        for test in self.DECODER_TESTS_M:
            self.do_test(test)

    def test_illegal(self):
        for test in self.DECODER_TESTS_ILLEGAL:
            self.do_test(test)

    def test_xintmachinemode(self):
        for test in self.DECODER_TESTS_XINTMACHINEMODE:
            self.do_test(test)

    def test_xintsupervisor(self):
        for test in self.DECODER_TESTS_XINTSUPERVISOR:
            self.do_test(test)

    def test_zbb(self):
        for test in self.DECODER_TESTS_ZBB:
            self.do_test(test)

    def test_v_integer(self):
        for test in self.DECODER_TESTS_V_INTEGERS:
            self.do_test(test)

    def test_v_control(self):
        for test in self.DECODER_TESTS_V_CONTROL:
            self.do_test(test)

    def test_v_memory(self):
        for test in self.DECODER_TESTS_V_MEMORY:
            self.do_test(test)


class TestDecoderEExtLegal(TestCaseWithSimulator):
    E_TEST = [
        (0x00000033, False),  # add x0, x0, x0
        (0x00F787B3, False),  # add x15, x15, x15
        (0x00F807B3, True),  # add x15, x16, x15
        (0xFFF78793, False),  # addi x15, x15, -1
        (0xFFF78813, True),  # addi x16, x15, -1
        (0xFFFFF06F, False),  # jal x0, -2
        (0xFFFFFF6F, True),  # jal x30, -2
    ]

    def test_e(self):
        gen = GenParams(test_core_config.replace(embedded=True, _implied_extensions=Extension.E))
        self.decoder = InstrDecoder(gen)

        def process():
            for encoding, illegal in self.E_TEST:
                yield self.decoder.instr.eq(encoding)
                yield Settle()
                self.assertEqual((yield self.decoder.illegal), illegal)

        with self.run_simulation(self.decoder) as sim:
            sim.add_process(process)


class TestEncodingUniqueness(TestCase):
    def test_encoding_uniqueness(self):
        code_type = tuple[Optional[int], Optional[int], Optional[int], Optional[int]]

        def instruction_code(instr: Encoding) -> code_type:
            op_code = int(instr.opcode)
            funct3 = int(instr.funct3) if instr.funct3 is not None else None
            funct7 = int(instr.funct7) if instr.funct7 is not None else None
            funct12_5bits = None

            if instr.funct12 is not None:
                funct7 = (int(instr.funct12) & 0xFE0) >> 5
                funct12_5bits = int(instr.funct12) & 0x1F

            if instr.funct6 is not None:
                funct7 = int(instr.funct6) * 2

            return (op_code, funct3, funct7, funct12_5bits)

        # prefixes of encoding
        def code_prefixes(code: code_type) -> list[code_type]:
            prefixes = []

            for i in range(3, -1, -1):
                if code[i] is not None:
                    nt = tuple(list(code[:i]) + [None] * (4 - i))

                    prefixes.append(nt)

            return prefixes

        # known_codes store insformation about already read encodings
        # if value is Encoding -> there is instruction with given code
        # if value is None -> there is an instruction with prefix equal to this code
        known_codes: dict[code_type, Optional[Encoding]] = dict()

        for instructions in _instructions_by_optype.values():
            for instruction in instructions:
                code = instruction_code(instruction)
                prefixes = code_prefixes(code)

                for prefix in prefixes:
                    if prefix in known_codes:
                        encoding = known_codes[prefix]

                        # prefix of instruction can not be equal to code of any other isntruction
                        self.assertIsNone(encoding, f"Instruction is not unique: I1 = {encoding} I2 = {instruction}")

                    known_codes[prefix] = None

                # current instruction can not be prefix of other instruction
                self.assertNotIn(code, known_codes, f"Instruction is not unique: I = {instruction}")

                known_codes[code] = instruction

    def test_decoded_distinguishable(self):
        code_type = tuple[Optional[int], Optional[int]]

        collisions: dict[OpType, set[Encoding]] = {
            OpType.ARITHMETIC: {
                Encoding(Opcode.OP_IMM, Funct3.ADD),
                Encoding(Opcode.LUI),
            },
            OpType.SHIFT: {
                Encoding(Opcode.OP_IMM, Funct3.SLL, Funct7.SL),
                Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SL),
                Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SA),
            },
            OpType.LOGIC: {
                Encoding(Opcode.OP_IMM, Funct3.XOR),
                Encoding(Opcode.OP_IMM, Funct3.OR),
                Encoding(Opcode.OP_IMM, Funct3.AND),
            },
            OpType.COMPARE: {
                Encoding(Opcode.OP_IMM, Funct3.SLT),
                Encoding(Opcode.OP_IMM, Funct3.SLTU),
            },
            OpType.SINGLE_BIT_MANIPULATION: {
                Encoding(Opcode.OP_IMM, Funct3.BCLR, Funct7.BCLR),
                Encoding(Opcode.OP_IMM, Funct3.BEXT, Funct7.BEXT),
                Encoding(Opcode.OP_IMM, Funct3.BSET, Funct7.BSET),
                Encoding(Opcode.OP_IMM, Funct3.BINV, Funct7.BINV),
            },
            OpType.BIT_MANIPULATION: {
                Encoding(Opcode.OP_IMM, Funct3.ROR, Funct7.ROR),
            },
        }

        def instruction_code(instr: Encoding) -> code_type:
            funct3 = int(instr.funct3) if instr.funct3 is not None else 0
            funct7 = int(instr.funct7) if instr.funct7 is not None else 0

            if instr.funct12 is not None:
                funct7 = (int(instr.funct12) & 0xFE0) >> 5

            if instr.funct6 is not None:
                funct7 = int(instr.funct6) * 2

            return (funct3, funct7)

        for ext, instructions in _instructions_by_optype.items():
            known_codes: set[code_type] = set()
            ext_collisions = collisions[ext] if ext in collisions else set()

            for instruction in instructions:
                if instruction in ext_collisions:
                    continue

                code = instruction_code(instruction)

                self.assertNotIn(
                    code, known_codes, f"Instruction is not unique within OpType: OpType={ext} I={instruction}"
                )

                known_codes.add(code)

            for instruction in ext_collisions:
                code = instruction_code(instruction)
                self.assertIn(code, known_codes, f"Instruction is not colliding: OpType={ext} I={instruction}")
