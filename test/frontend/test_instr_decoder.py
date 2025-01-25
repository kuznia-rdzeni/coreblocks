from amaranth.sim import *

from transactron.testing import TestCaseWithSimulator, TestbenchContext

from coreblocks.params import *
from coreblocks.params.configurations import test_core_config
from coreblocks.frontend.decoder.instr_decoder import InstrDecoder, Encoding, instructions_by_optype
from coreblocks.arch import *
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
        # InstrTest(0x10500073, Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.WFI, op=OpType.WFI),
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
    DECODER_TESTS_ZICOND = [
        #      CZERO    RS2   RS1   EQZ   RD     OP
        # nez 0b0000111 00000 00000 111 00000 0110011
        # eqz 0b0000111 00000 00000 101 00000 0110011
        # CZERO.NEZ
        InstrTest(0x0E007033, Opcode.OP, Funct3.CZERONEZ, Funct7.CZERO, rd=0, rs1=0, rs2=0, op=OpType.CZERO),
        # CZERO.EQZ
        InstrTest(0x0E005033, Opcode.OP, Funct3.CZEROEQZ, Funct7.CZERO, rd=0, rs1=0, rs2=0, op=OpType.CZERO),
    ]

    DECODER_TESTS_A = [
        InstrTest(0x0821A22F, Opcode.AMO, Funct3.W, Funct7.AMOSWAP, rd=4, rs2=2, rs1=3, op=OpType.ATOMIC_MEMORY_OP),
        InstrTest(
            0x0C21A22F, Opcode.AMO, Funct3.W, Funct7.AMOSWAP | 0x2, rd=4, rs2=2, rs1=3, op=OpType.ATOMIC_MEMORY_OP
        ),
        InstrTest(0x1812A1AF, Opcode.AMO, Funct3.W, Funct7.SC, rd=3, rs2=1, rs1=5, op=OpType.ATOMIC_LR_SC),
    ]

    def setup_method(self):
        self.gen_params = GenParams(
            test_core_config.replace(
                _implied_extensions=Extension.G
                | Extension.XINTMACHINEMODE
                | Extension.XINTSUPERVISOR
                | Extension.ZBB
                | Extension.ZICOND
            )
        )
        self.decoder = InstrDecoder(self.gen_params)
        self.cnt = 1

    def do_test(self, tests: list[InstrTest]):
        async def process(sim: TestbenchContext):
            for test in tests:
                sim.set(self.decoder.instr, test.encoding)

                assert sim.get(self.decoder.illegal) == test.illegal
                if test.illegal:
                    return

                assert sim.get(self.decoder.opcode) == test.opcode

                if test.funct3 is not None:
                    assert sim.get(self.decoder.funct3) == test.funct3
                assert sim.get(self.decoder.funct3_v) == (test.funct3 is not None)

                if test.funct7 is not None:
                    assert sim.get(self.decoder.funct7) == test.funct7
                assert sim.get(self.decoder.funct7_v) == (test.funct7 is not None)

                if test.funct12 is not None:
                    assert sim.get(self.decoder.funct12) == test.funct12
                assert sim.get(self.decoder.funct12_v) == (test.funct12 is not None)

                if test.rd is not None:
                    assert sim.get(self.decoder.rd) == test.rd
                assert sim.get(self.decoder.rd_v) == (test.rd is not None)

                if test.rs1 is not None:
                    assert sim.get(self.decoder.rs1) == test.rs1
                assert sim.get(self.decoder.rs1_v) == (test.rs1 is not None)

                if test.rs2 is not None:
                    assert sim.get(self.decoder.rs2) == test.rs2
                assert sim.get(self.decoder.rs2_v) == (test.rs2 is not None)

                if test.imm is not None:
                    if test.csr is not None:
                        # in CSR instruction additional fields are passed in unused bits of imm field
                        assert sim.get(self.decoder.imm.as_signed() & ((2**5) - 1)) == test.imm
                    else:
                        assert sim.get(self.decoder.imm.as_signed()) == test.imm

                if test.succ is not None:
                    assert sim.get(self.decoder.succ) == test.succ

                if test.pred is not None:
                    assert sim.get(self.decoder.pred) == test.pred

                if test.fm is not None:
                    assert sim.get(self.decoder.fm) == test.fm

                if test.csr is not None:
                    assert sim.get(self.decoder.csr) == test.csr

                assert sim.get(self.decoder.optype) == test.op

        with self.run_simulation(self.decoder) as sim:
            sim.add_testbench(process)

    def test_i(self):
        self.do_test(self.DECODER_TESTS_I)

    def test_zifencei(self):
        self.do_test(self.DECODER_TESTS_ZIFENCEI)

    def test_zicsr(self):
        self.do_test(self.DECODER_TESTS_ZICSR)

    def test_m(self):
        self.do_test(self.DECODER_TESTS_M)

    def test_illegal(self):
        self.do_test(self.DECODER_TESTS_ILLEGAL)

    def test_xintmachinemode(self):
        self.do_test(self.DECODER_TESTS_XINTMACHINEMODE)

    def test_xintsupervisor(self):
        self.do_test(self.DECODER_TESTS_XINTSUPERVISOR)

    def test_zbb(self):
        self.do_test(self.DECODER_TESTS_ZBB)

    def test_zicond(self):
        self.do_test(self.DECODER_TESTS_ZICOND)

    def test_a(self):
        self.do_test(self.DECODER_TESTS_A)


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
        self.gen_params = GenParams(test_core_config.replace(embedded=True, _implied_extensions=Extension.E))
        self.decoder = InstrDecoder(self.gen_params)

        async def process(sim: TestbenchContext):
            for encoding, illegal in self.E_TEST:
                sim.set(self.decoder.instr, encoding)
                assert sim.get(self.decoder.illegal) == illegal

        with self.run_simulation(self.decoder) as sim:
            sim.add_testbench(process)


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

        for instructions in instructions_by_optype.values():
            for instruction in instructions:
                code = instruction_code(instruction)
                prefixes = code_prefixes(code)

                for prefix in prefixes:
                    if prefix in known_codes:
                        encoding = known_codes[prefix]

                        # prefix of instruction can not be equal to code of any other isntruction
                        assert encoding is None, f"Instruction is not unique: I1 = {encoding} I2 = {instruction}"

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
            OpType.BIT_ROTATION: {
                Encoding(Opcode.OP_IMM, Funct3.ROR, Funct7.ROR),
            },
        }

        def instruction_code(instr: Encoding) -> code_type:
            funct3 = int(instr.funct3) if instr.funct3 is not None else 0
            funct7 = int(instr.funct7) if instr.funct7 is not None else 0

            if instr.funct12 is not None:
                funct7 = (int(instr.funct12) & 0xFE0) >> 5

            return (funct3, funct7)

        for ext, instructions in instructions_by_optype.items():
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
                assert code in known_codes, f"Instruction is not colliding: OpType={ext} I={instruction}"
