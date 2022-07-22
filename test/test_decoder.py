from amaranth import *
from amaranth.sim import *

from .common import TestCaseWithSimulator

from coreblocks.genparams import GenParams
from coreblocks.isa import *
from coreblocks.decoder import InstrDecoder


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
            rs1=None,
            rs2=None,
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
            self.rs1 = rs1
            self.rs2 = rs2
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
        InstrTest(0x001230B7, Opcode.OP_IMM, Funct3.ADD, rd=1, imm=0x123 << 12, op=OpType.ARITHMETIC),
        # Compare
        InstrTest(0x07BF2A13, Opcode.OP_IMM, Funct3.SLT, rd=20, rs1=30, imm=123, op=OpType.COMPARE),
        InstrTest(0x0FFFBA93, Opcode.OP_IMM, Funct3.SLTU, rd=21, rs1=31, imm=0xFF, op=OpType.COMPARE),
        InstrTest(0x00C5A533, Opcode.OP, Funct3.SLT, Funct7.SLT, rd=10, rs1=11, rs2=12, op=OpType.COMPARE),
        InstrTest(0x00C5B533, Opcode.OP, Funct3.SLTU, Funct7.SLT, rd=10, rs1=11, rs2=12, op=OpType.COMPARE),
        # Logic
        InstrTest(0xFFF04013, Opcode.OP_IMM, Funct3.XOR, rd=0, rs1=0, imm=0xFFFFFFFF, op=OpType.LOGIC),
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
        # Jump
        InstrTest(0x000000EF, Opcode.JAL, rd=1, imm=0, op=OpType.JUMP),
        InstrTest(0xFFE100E7, Opcode.JALR, Funct3.JALR, rd=1, rs1=2, imm=0xFFFFFFFE, op=OpType.JUMP),
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
        InstrTest(0x00000073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.ECALL, rd=0, rs1=0, op=OpType.ECALL),
        # EBREAK
        InstrTest(0x00100073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.EBREAK, rd=0, rs1=0, op=OpType.EBREAK),
        # MRET
        InstrTest(0x30200073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.MRET, rd=0, rs1=0, op=OpType.MRET),
        # WFI
        InstrTest(0x10500073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.WFI, rd=0, rs1=0, op=OpType.WFI),
    ]
    DECODER_TESTS_ZIFENCEI = [
        InstrTest(0x0000100F, Opcode.MISC_MEM, Funct3.FENCEI, rd=0, rs1=0, imm=0, op=OpType.FENCEI),
    ]
    DECODER_TESTS_ZICSR = [
        InstrTest(0x001A9A73, Opcode.SYSTEM, Funct3.CSRRW, rd=20, rs1=21, csr=0x01, op=OpType.CSR),
        InstrTest(0x002B2AF3, Opcode.SYSTEM, Funct3.CSRRS, rd=21, rs1=22, csr=0x02, op=OpType.CSR),
        InstrTest(0x004BBB73, Opcode.SYSTEM, Funct3.CSRRC, rd=22, rs1=23, csr=0x04, op=OpType.CSR),
        InstrTest(0x001FDA73, Opcode.SYSTEM, Funct3.CSRRWI, rd=20, imm=0x1F, csr=0x01, op=OpType.CSR),
        InstrTest(0x0027EAF3, Opcode.SYSTEM, Funct3.CSRRSI, rd=21, imm=0xF, csr=0x02, op=OpType.CSR),
        InstrTest(0x00407B73, Opcode.SYSTEM, Funct3.CSRRCI, rd=22, imm=0x0, csr=0x04, op=OpType.CSR),
    ]
    DECODER_TESTS_ILLEGAL = [
        InstrTest(0xFFFFFFFF, Opcode.OP_IMM, illegal=1),
        InstrTest(0x003160FF, Opcode.OP, Funct3.OR, Funct7.OR, rd=1, rs1=2, rs2=3, op=OpType.LOGIC, illegal=1),
    ]

    def setUp(self):
        gen = GenParams("rv32gc")
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

            self.assertEqual((yield self.decoder.funct3), test.funct3 if test.funct3 is not None else 0)
            self.assertEqual((yield self.decoder.funct3_v), test.funct3 is not None)

            self.assertEqual((yield self.decoder.funct7), test.funct7 if test.funct7 is not None else 0)
            self.assertEqual((yield self.decoder.funct7_v), test.funct7 is not None)

            self.assertEqual((yield self.decoder.funct12), test.funct12 if test.funct12 is not None else 0)
            self.assertEqual((yield self.decoder.funct12_v), test.funct12 is not None)

            if test.rd is not None:
                self.assertEqual((yield self.decoder.rd_v), 1)
                self.assertEqual((yield self.decoder.rd), test.rd)

            if test.rs1 is not None:
                self.assertEqual((yield self.decoder.rs1_v), 1)
                self.assertEqual((yield self.decoder.rs1), test.rs1)

            if test.rs2 is not None:
                self.assertEqual((yield self.decoder.rs2_v), 1)
                self.assertEqual((yield self.decoder.rs2), test.rs2)

            if test.imm is not None:
                self.assertEqual((yield self.decoder.imm), test.imm)

            if test.succ is not None:
                self.assertEqual((yield self.decoder.succ), test.succ)

            if test.pred is not None:
                self.assertEqual((yield self.decoder.pred), test.pred)

            if test.fm is not None:
                self.assertEqual((yield self.decoder.fm), test.fm)

            if test.csr is not None:
                self.assertEqual((yield self.decoder.csr), test.csr)

            self.assertEqual((yield self.decoder.op), test.op)

        with self.runSimulation(self.decoder) as sim:
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

    def test_illegal(self):
        for test in self.DECODER_TESTS_ILLEGAL:
            self.do_test(test)
