from amaranth.sim import *

from ..common import TestCaseWithSimulator

from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.frontend.decoder import InstrDecoder


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
            rd_rf = RegisterType.X,
            rs1=None,
            rs1_rf = RegisterType.X,
            rs2=None,
            rs2_rf = RegisterType.X,
            imm=None,
            succ=None,
            pred=None,
            fm=None,
            csr=None,
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
            self.csr = csr
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
        InstrTest(0x001A9A73, Opcode.SYSTEM, Funct3.CSRRW, rd=20, rs1=21, csr=0x01, op=OpType.CSR_REG),
        InstrTest(0x002B2AF3, Opcode.SYSTEM, Funct3.CSRRS, rd=21, rs1=22, csr=0x02, op=OpType.CSR_REG),
        InstrTest(0x004BBB73, Opcode.SYSTEM, Funct3.CSRRC, rd=22, rs1=23, csr=0x04, op=OpType.CSR_REG),
        InstrTest(0x001FDA73, Opcode.SYSTEM, Funct3.CSRRWI, rd=20, imm=0x1F, csr=0x01, op=OpType.CSR_IMM),
        InstrTest(0x0027EAF3, Opcode.SYSTEM, Funct3.CSRRSI, rd=21, imm=0xF, csr=0x02, op=OpType.CSR_IMM),
        InstrTest(0x00407B73, Opcode.SYSTEM, Funct3.CSRRCI, rd=22, imm=0x0, csr=0x04, op=OpType.CSR_IMM),
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
        InstrTest(0x022180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VADD * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vadd.vv v1, v2, v3
        InstrTest(0x002180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VADD * 2 + 1, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vadd.vv v1, v2, v3, v0.t
        InstrTest(0x0245b057, Opcode.OP_V, Funct3.OPIVI, Funct6.VADD * 2, rd_rf=RegisterType.V, rd= 0, rs2_rf=RegisterType.V, rs2= 4, imm=11, op=OpType.V_ARITHMETIC_IMM), #vadd.vi v0, v4, 11
        InstrTest(0x0283cfd7, Opcode.OP_V, Funct3.OPIVX, Funct6.VADD * 2, rd_rf=RegisterType.V, rd= 3, rs2_rf=RegisterType.V, rs2= 8, rs1_rf=RegisterType.X, rs1=7, op=OpType.V_ARITHMETIC_SCALAR), #vadd.vx v31, v8, x7
        InstrTest(0x0083cfd7, Opcode.OP_V, Funct3.OPIVX, Funct6.VADD * 2 + 1, rd_rf=RegisterType.V, rd= 3, rs2_rf=RegisterType.V, rs2= 8, rs1_rf=RegisterType.X, rs1=7, op=OpType.V_ARITHMETIC_SCALAR), #vadd.vx v31, v8, x7, v0.t
        InstrTest(0x0a818257, Opcode.OP_V, Funct3.OPIVV, Funct6.VSUB * 2, rd_rf=RegisterType.V, rd= 4, rs2_rf=RegisterType.V, rs2= 8, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vsub.vv v4, v8, v3
        InstrTest(0x0a30c157, Opcode.OP_V, Funct3.OPIVX, Funct6.VSUB * 2, rd_rf=RegisterType.V, rd= 2, rs2_rf=RegisterType.V, rs2= 3, rs1_rf=RegisterType.V, rs1=1, op=OpType.V_ARITHMETIC), #vsub.vx v2, v3, x1
        InstrTest(0x0e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VRSUB * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vrsub.vx v1, v2, x3
        InstrTest(0x0e23b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VRSUB * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=7, op=OpType.V_ARITHMETIC_IMM), #vrsub.vi v1, v2, 7
        InstrTest(0x122180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMINU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vminu.vv v1, v2, v3
        InstrTest(0x1221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMINU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vminu.vx v1, v2, x3
        InstrTest(0x162180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMIN * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmin.vv v1, v2, v3
        InstrTest(0x1621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMIN * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmin.vx v1, v2, x3
        InstrTest(0x1a2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMAXU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmaxu.vv v1, v2, v3
        InstrTest(0x1a21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMAXU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmaxu.vx v1, v2, x3
        InstrTest(0x1e2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMAX * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmax.vv v1, v2, v3
        InstrTest(0x1e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMAX * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmax.vx v1, v2, x3
        InstrTest(0x262180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VAND * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vand.vv v1, v2, v3
        InstrTest(0x2621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VAND * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vand.vx v1, v2, x3
        InstrTest(0x2627b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VAND * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=15, op=OpType.V_ARITHMETIC_IMM), #vand.vi v1, v2, 15
        InstrTest(0x2a2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VOR * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vor.vv v1, v2, v3
        InstrTest(0x2a21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VOR * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vor.vx v1, v2, x3
        InstrTest(0x2a2830d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VOR * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=-16, op=OpType.V_ARITHMETIC_IMM), #vor.vi v1, v2, -16
        InstrTest(0x2e2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VXOR * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vxor.vv v1, v2, v3
        InstrTest(0x2e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VXOR * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vxor.vx v1, v2, x3
        InstrTest(0x2e2030d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VXOR * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=0, op=OpType.V_ARITHMETIC_IMM), #vxor.vi v1, v2, 0
        InstrTest(0x322180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VRGATHER * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vrgather.vv v1, v2, v3
        InstrTest(0x3221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VRGATHER * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vrgather.vx v1, v2, x3
        InstrTest(0x322230d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VRGATHER * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=4, op=OpType.V_ARITHMETIC_IMM), #vrgather.vi v1, v2, 4
        InstrTest(0x3a21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSLIDEUP * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vslideup.vx v1, v2, x3
        InstrTest(0x3a2130d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSLIDEUP * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=2, op=OpType.V_ARITHMETIC_IMM), #vslideup.vi v1, v2, 2
        InstrTest(0x3a2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VRGATHEREI16 * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vrgatherei16.vv v1, v2, v3
        InstrTest(0x3e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSLIDEDOWN * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vslidedown.vx v1, v2, x3
        InstrTest(0x3e2130d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSLIDEDOWN * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=2, op=OpType.V_ARITHMETIC_IMM), #vslidedown.vi v1, v2, 2
        InstrTest(0x402180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VADC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vadc.vvm v1, v2, v3, v0
        InstrTest(0x4021c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VADC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vadc.vxm v1, v2, x3, v0
        InstrTest(0x4021b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VADC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=3, op=OpType.V_ARITHMETIC_IMM), #vadc.vim v1, v2, 3, v0
        InstrTest(0x442180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMADC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmadc.vvm v1, v2, v3, v0
        InstrTest(0x4421c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMADC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmadc.vxm v1, v2, x3, v0
        InstrTest(0x4421b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMADC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmadc.vim v1, v2, 3, v0
        InstrTest(0x482180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSBC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vsbc.vvm v1, v2, v3, v0
        InstrTest(0x4821c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSBC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vsbc.vxm v1, v2, x3, v0
        InstrTest(0x4c2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSBC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmsbc.vvm v1, v2, v3, v0
        InstrTest(0x4c21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSBC * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsbc.vxm v1, v2, x3, v0
        InstrTest(0x5c2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMERGE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmerge.vvm v1, v2, v3, v0
        InstrTest(0x5c21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMERGE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmerge.vxm v1, v2, x3, v0
        InstrTest(0x5c21b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMERGE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmerge.vim v1, v2, 3, v0
        InstrTest(0x5e0180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMV * 2 + 1, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2=0, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmv.v.v v1, v3
        InstrTest(0x5e01c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMV * 2 + 1, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2=0, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmv.v.x v1, x3
        InstrTest(0x5e01b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMV * 2 + 1, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2=0, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmv.v.i v1, 3
        InstrTest(0x622180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSEQ * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmseq.vv v1, v2, v3
        InstrTest(0x6221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSEQ * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmseq.vx v1, v2, x3
        InstrTest(0x6221b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMSEQ * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmseq.vi v1, v2, 3
        InstrTest(0x662180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSNE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmsne.vv v1, v2, v3
        InstrTest(0x6621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSNE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsne.vx v1, v2, x3
        InstrTest(0x6621b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMSNE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmsne.vi v1, v2, 3
        InstrTest(0x6a2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSLTU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmsltu.vv v1, v2, v3
        InstrTest(0x6a21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSLTU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsltu.vx v1, v2, x3
        InstrTest(0x6e2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSLT * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmslt.vv v1, v2, v3
        InstrTest(0x6e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSLT * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=33, op=OpType.V_ARITHMETIC_SCALAR), #vmslt.vx v1, v2, x3
        InstrTest(0x722180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSLEU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmsleu.vv v1, v2, v3
        InstrTest(0x7221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSLEU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsleu.vx v1, v2, x3
        InstrTest(0x7221b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMSLEU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmsleu.vi v1, v2, 3
        InstrTest(0x762180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VMSLE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vmsle.vv v1, v2, v3
        InstrTest(0x7621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSLE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsle.vx v1, v2, x3
        InstrTest(0x7621b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMSLE * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vmsle.vi v1, v2, 3
        InstrTest(0x7a21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSGTU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsgtu.vx v1, v2, x3
        InstrTest(0x7a21b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMSGTU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vmsgtu.vi v1, v2, 3
        InstrTest(0x7e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VMSGT * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vmsgt.vx v1, v2, x3
        InstrTest(0x7e21b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VMSGT * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vmsgt.vi v1, v2, 3
        InstrTest(0x822180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSADDU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vsaddu.vv v1, v2, v3
        InstrTest(0x8221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSADDU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vsaddu.vx v1, v2, x3
        InstrTest(0x8221b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSADDU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vsaddu.vi v1, v2, 3
        InstrTest(0x862180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSADD * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vsadd.vv v1, v2, v3
        InstrTest(0x8621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSADD * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vsadd.vx v1, v2, x3
        InstrTest(0x8621b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSADD * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vsadd.vi v1, v2, 3
        InstrTest(0x8a2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSSUBU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vssubu.vv v1, v2, v3
        InstrTest(0x8a21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSSUBU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vssubu.vx v1, v2, x3
        InstrTest(0x8e2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSSUB * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vssub.vv v1, v2, v3
        InstrTest(0x8e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSSUB * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1=3, op=OpType.V_ARITHMETIC_SCALAR), #vssub.vx v1, v2, x3
        InstrTest(0x962180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSLL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vsll.vv v1, v2, v3
        InstrTest(0x9621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSLL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vsll.vx v1, v2, x3
        InstrTest(0x9621b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSLL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vsll.vi v1, v2, 3
        InstrTest(0x9e2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSMUL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vsmul.vv v1, v2, v3
        InstrTest(0x9e21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSMUL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vsmul.vx v1, v2, x3
        InstrTest(0x9e803057, Opcode.OP_V, Funct3.OPIVI, Funct6.VMV1R * 2 + 1, rd_rf=RegisterType.V, rd= 0,  rs2_rf=RegisterType.V, rs2=8, imm=0, op=OpType.V_ARITHMETIC_IMM), #vmv1r.v v0, v8
        InstrTest(0x9e80b057, Opcode.OP_V, Funct3.OPIVI, Funct6.VMV2R * 2 + 1, rd_rf=RegisterType.V, rd= 0,  rs2_rf=RegisterType.V, rs2=8, imm=1, op=OpType.V_ARITHMETIC_IMM), #vmv2r.v v0, v8
        InstrTest(0x9e81b057, Opcode.OP_V, Funct3.OPIVI, Funct6.VMV4R * 2 + 1, rd_rf=RegisterType.V, rd= 0,  rs2_rf=RegisterType.V, rs2=8, imm=3, op=OpType.V_ARITHMETIC_IMM), #vmv4r.v v0, v8
        InstrTest(0x9e83b057, Opcode.OP_V, Funct3.OPIVI, Funct6.VMV8R * 2 + 1, rd_rf=RegisterType.V, rd= 0,  rs2_rf=RegisterType.V, rs2=8, imm=7, op=OpType.V_ARITHMETIC_IMM), #vmv8r.v v0, v8
        InstrTest(0xa22180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSRL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC), #vsrl.vv v1, v2, v3
        InstrTest(0xa221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSRL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vsrl.vx v1, v2, x3
        InstrTest(0xa221b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSRL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vsrl.vi v1, v2, 3
        InstrTest(0xa62180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VSRA * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC), #vsra.vv v1, v2, v3
        InstrTest(0xa621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VSRA * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vsra.vx v1, v2, x3
        InstrTest(0xa621b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VSRA * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, imm= 3, op=OpType.V_ARITHMETIC_IMM), #vsra.vi v1, v2, 3
        InstrTest(0xb22180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VNSRL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vnsrl.wv v1, v2, v3
        InstrTest(0xb221c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VNSRL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vnsrl.wx v1, v2, x3
        InstrTest(0xb221b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VNSRL * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC_IMM), #vnsrl.wi v1, v2, 3
        InstrTest(0xb62180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VNSRA * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC), #vnsra.wv v1, v2, v3
        InstrTest(0xb621c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VNSRA * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vnsra.wx v1, v2, x3
        InstrTest(0xb621b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VNSRA * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC_IMM), #vnsra.wi v1, v2, 3
        InstrTest(0xba2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VNCLIPU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC), #vnclipu.wv v1, v2, v3
        InstrTest(0xba21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VNCLIPU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vnclipu.wx v1, v2, x3
        InstrTest(0xba21b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VNCLIPU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC_IMM), #vnclipu.wi v1, v2, 3
        InstrTest(0xbe2180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VNCLIP * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC), #vnclip.wv v1, v2, v3
        InstrTest(0xbe21c0d7, Opcode.OP_V, Funct3.OPIVX, Funct6.VNCLIP * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.X, rs1= 3, op=OpType.V_ARITHMETIC_SCALAR), #vnclip.wx v1, v2, x3
        InstrTest(0xbe21b0d7, Opcode.OP_V, Funct3.OPIVI, Funct6.VNCLIP * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC_IMM), #vnclip.wi v1, v2, 3
        InstrTest(0xc22180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VWREDSUMU * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1=3, op=OpType.V_ARITHMETIC), #vwredsumu.vs v1, v2, v3
        InstrTest(0xc62180d7, Opcode.OP_V, Funct3.OPIVV, Funct6.VWREDSUM * 2, rd_rf=RegisterType.V, rd= 1, rs2_rf=RegisterType.V, rs2= 2, rs1_rf=RegisterType.V, rs1= 3, op=OpType.V_ARITHMETIC),#vwredsum.vs v1, v2, v3
    ]
    DECODER_TESTS_V_CONTROL = [
        InstrTest(0x8020f057, Opcode.OP_V, Funct3.OPCFG, rd=0, rs1=1, rs2=2, op=OpType.V_CONTROL), #vsetvl x0, x1, x2
        InstrTest(0x0d307057, Opcode.OP_V, Funct3.OPCFG, rd=0, rs1=0, csr=0b11010011, op=OpType.V_CONTROL), #vsetvli x0, x0, e32,m8,ta,ma
        InstrTest(0xcd3470d7, Opcode.OP_V, Funct3.OPCFG, rd=1, imm=8, csr=0b110011010011,op=OpType.V_CONTROL), #vsetivli x1, 8, e32,m8,ta,ma
    ]


    def setUp(self):
        gen = GenParams(
            test_core_config.replace(
                _implied_extensions=Extension.G | Extension.XINTMACHINEMODE | Extension.XINTSUPERVISOR | Extension.ZBB
            )
        )
        self.decoder = InstrDecoder(gen)
        self.cnt = 1

    def do_test(self, test):
        def process():
            yield self.decoder.instr.eq(test.encoding)
            yield Settle()

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
                self.assertEqual((yield self.decoder.rd_rf), test.rd_rf)
            self.assertEqual((yield self.decoder.rd_v), test.rd is not None)

            if test.rs1 is not None:
                self.assertEqual((yield self.decoder.rs1), test.rs1)
                self.assertEqual((yield self.decoder.rs1_rf), test.rs1_rf)
            self.assertEqual((yield self.decoder.rs1_v), test.rs1 is not None)

            if test.rs2 is not None:
                self.assertEqual((yield self.decoder.rs2), test.rs2)
                self.assertEqual((yield self.decoder.rs2_rf), test.rs2_rf)
            self.assertEqual((yield self.decoder.rs2_v), test.rs2 is not None)

            if test.imm is not None:
                self.assertEqual((yield self.decoder.imm.as_signed()), test.imm)

            if test.succ is not None:
                self.assertEqual((yield self.decoder.succ), test.succ)

            if test.pred is not None:
                self.assertEqual((yield self.decoder.pred), test.pred)

            if test.fm is not None:
                self.assertEqual((yield self.decoder.fm), test.fm)

            if test.csr is not None:
                self.assertEqual((yield self.decoder.csr), test.csr)

            self.assertEqual((yield self.decoder.optype), test.op)

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
