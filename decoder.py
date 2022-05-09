from functools import reduce
from itertools import starmap
from operator import or_

from amaranth import *

from .isa import *


__all__ = ["InstrDecoder"]


_rd_itypes = [
    InstrType.R, InstrType.I, InstrType.U, InstrType.J
]

_rs1_itypes = [
    InstrType.R, InstrType.I, InstrType.S, InstrType.B
]

_rs2_itypes = [
    InstrType.R, InstrType.S, InstrType.B
]


class Encoding:
    def __init__(self, opcode, funct3=None, funct7=None, funct12=None):
        assert isinstance(opcode, Opcode)
        self.opcode = opcode

        assert (funct3 is None) or isinstance(funct3, Funct3)
        self.funct3 = funct3

        assert (funct7 is None) or isinstance(funct7, Funct7)
        self.funct7 = funct7

        assert (funct12 is None) or isinstance(funct12, Funct12)
        self.funct12 = funct12


_arithmetic_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.ADD),             # addi
    Encoding(Opcode.OP,     Funct3.ADD, Funct7.ADD), # add
    Encoding(Opcode.OP,     Funct3.ADD, Funct7.SUB), # sub
]

_compare_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.SLT),              # slti
    Encoding(Opcode.OP_IMM, Funct3.SLTU),             # sltiu
    Encoding(Opcode.OP,     Funct3.SLT, Funct7.SLT),  # slt
    Encoding(Opcode.OP,     Funct3.SLTU, Funct7.SLT), # sltu
]

_logic_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.XOR),             # xori
    Encoding(Opcode.OP_IMM, Funct3.OR),              # ori
    Encoding(Opcode.OP_IMM, Funct3.AND),             # andi
    Encoding(Opcode.OP,     Funct3.XOR, Funct7.XOR), # xor
    Encoding(Opcode.OP,     Funct3.OR,  Funct7.OR),  # or
    Encoding(Opcode.OP,     Funct3.AND, Funct7.AND), # and
]

_shift_encodings = [
    Encoding(Opcode.OP_IMM, Funct3.SLL, Funct7.SL), # slli
    Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SL),  # srli
    Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SA),  # srai
    Encoding(Opcode.OP,     Funct3.SLL, Funct7.SL), # sll
    Encoding(Opcode.OP,     Funct3.SR, Funct7.SL),  # srl
    Encoding(Opcode.OP,     Funct3.SR, Funct7.SA),  # sra
]

_auipc_encodings = [
    Encoding(Opcode.AUIPC), # auipc
]

_lui_encodings = [
    Encoding(Opcode.LUI), # lui
]

_jump_encodings = [
    Encoding(Opcode.JAL),     # jal
    Encoding(Opcode.JALR, Funct3.JALR), # jalr
]

_branch_encodings = [
    Encoding(Opcode.BRANCH, Funct3.BEQ),  # beq
    Encoding(Opcode.BRANCH, Funct3.BNE),  # bne
    Encoding(Opcode.BRANCH, Funct3.BLT),  # blt
    Encoding(Opcode.BRANCH, Funct3.BGE),  # bge
    Encoding(Opcode.BRANCH, Funct3.BLTU), # bltu
    Encoding(Opcode.BRANCH, Funct3.BGEU), # bgeu
]

_load_encodings = [
    Encoding(Opcode.LOAD, Funct3.B),  # lb
    Encoding(Opcode.LOAD, Funct3.BU), # lbu
    Encoding(Opcode.LOAD, Funct3.H),  # lh
    Encoding(Opcode.LOAD, Funct3.HU), # lhu
    Encoding(Opcode.LOAD, Funct3.W),  # lw
]

_store_encodings = [
    Encoding(Opcode.STORE, Funct3.B), # sb
    Encoding(Opcode.STORE, Funct3.H), # sh
    Encoding(Opcode.STORE, Funct3.W), # sw
]

_ifence_encodings = [
    Encoding(Opcode.MISC_MEM, Funct3.FENCEI), # fence.i
]

_ecall_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.ECALL), # ecall
]

_ebreak_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.EBREAK), # ebreak
]

_mret_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.MRET), # mret
]

_csr_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.CSRRW),  # csrrw
    Encoding(Opcode.SYSTEM, Funct3.CSRRS),  # csrrs
    Encoding(Opcode.SYSTEM, Funct3.CSRRC),  # csrrc
    Encoding(Opcode.SYSTEM, Funct3.CSRRWI), # csrrwi
    Encoding(Opcode.SYSTEM, Funct3.CSRRSI), # csrrsi
    Encoding(Opcode.SYSTEM, Funct3.CSRRCI), # csrrci
]

_wfi_encodings = [
    Encoding(Opcode.SYSTEM, Funct3.PRIV, None, Funct12.WFI), # wfi
]


class InstrDecoder(Elaboratable):
    def __init__(self):
        # Input ports

        self.instr = Signal(INSTR_LEN)

        # Output ports

        # Opcode and funct
        self.opcode = Signal(Opcode)
        self.funct3 = Signal(Funct3)
        self.funct7 = Signal(Funct7)
        self.funct12 = Signal(Funct12)

        # Destination register
        self.rd = Signal(range(GPR_CNT))
        self.rd_v = Signal()

        # First source register
        self.rs1 = Signal(range(GPR_CNT))
        self.rs1_v = Signal()

        # Second source register
        self.rs2 = Signal(range(GPR_CNT))
        self.rs2_v = Signal()

        # Immediate
        self.imm = Signal(GPR_WIDTH)

        # Operation type
        self.op = Signal(OpType)

        # Illegal instruction
        self.illegal = Signal()

    def _extract(self, start, sig):
        sig.eq(self.instr[start:start+len(sig)])

    def _match(self, encodings):
        return reduce(or_, starmap(
            lambda enc:
                (self.opcode == enc.opcode if enc.opcode is not None else 1) & \
                (self.funct3 == enc.funct3 if enc.funct3 is not None else 1) & \
                (self.funct7 == enc.funct7 if enc.funct7 is not None else 1) & \
                (self.funct12 == enc.funct12 if enc.funct12 is not Nonde else 1) & \
                ((self.rd == 0) & (self.rs1 == 0) if enc.funct3 == Funct3.PRIV else 1),
            encodings))

    def elaborate(self, platform):
        m = Module()

        # Opcode and funct

        m.d.comb += [
            self._extract(2, self.opcode),
            self._extract(12, self.funct3),
            self._extract(25, self.funct7),
            self._extract(20, self.funct12),
        ]

        # Instruction type

        itype = Signal(InstrType)

        with m.Switch(self.opcode):
            with m.Case(Opcode.OP_IMM):
                m.d.comb += itype.eq(InstrType.I)
            with m.Case(Opcode.LUI):
                m.d.comb += itype.eq(InstrType.U)
            with m.Case(Opcode.AUIPC):
                m.d.comb += itype.eq(InstrType.U)
            with m.Case(Opcode.OP):
                m.d.comb += itype.eq(InstrType.R)
            with m.Case(Opcode.JAL):
                m.d.comb += itype.eq(InstrType.J)
            with m.Case(Opcode.JALR):
                m.d.comb += itype.eq(InstrType.I)
            with m.Case(Opcode.BRANCH):
                m.d.comb += itype.eq(InstrType.B)
            with m.Case(Opcode.LOAD):
                m.d.comb += itype.eq(InstrType.I)
            with m.Case(Opcode.STORE):
                m.d.comb += itype.eq(InstrType.S)
            with m.Case(Opcode.MISC_MEM):
                m.d.comb += itype.eq(InstrType.I)
            with m.Case(Opcode.SYSTEM):
                m.d.comb += itype.eq(InstrType.I)

        # Destination and source registers

        m.d.comb += [
            self._extract(7, self.rd),
            self.rd_v.eq(reduce(or_, (itype == t for t in _rd_itypes))),

            self._extract(15, self.rs1),
            self.rs1_v.eq(reduce(or_, (itype == t for t in _rs1_itypes))),

            self._extract(20, self.rs2),
            self.rs2_v.eq(reduce(or_, (itype == t for t in _rs2_itypes))),
        ]

        # Immediate

        iimm12 = Signal(signed(12))
        simm12 = Signal(signed(12))
        bimm13 = Signal(signed(13))
        uimm20 = Signal(unsigned(20))
        jimm20 = Signal(signed(21))

        m.d.comb += [
            self._extract(20, iimm12),
            simm12.eq(Cat(instr[7:12], instr[25:32])),
            bimm12.eq(Cat(0, instr[8:12], instr[25:31], instr[7], instr[31])),
            self._extract(12, uimm20),
            jimm20.eq(Cat(0, instr[21:31], instr[20], instr[12:20], instr[31])),
        ]

        with m.Switch(itype):
            with m.Case(InstrType.I):
                m.d.comb += self.imm.eq(iimm12)
            with m.Case(InstrType.S):
                m.d.comb += self.imm.eq(simm12)
            with m.Case(InstrType.B):
                m.d.comb += self.imm.eq(bimm12)
            with m.Case(InstrType.U):
                m.d.comb += self.imm.eq(uimm20 << (GPR_WIDTH-20))
            with m.Case(InstrType.J):
                m.d.comb += self.imm.eq(jimm20)

        # Operation type

        m.d.comb += self.op.eq(OpType.UNKNOWN)

        with m.If(self.match(_arithmetic_encodings)):
            m.d.comb += self.op.eq(OpType.ARITHMETIC)
        with m.Elif(self.match(_compare_encodings)):
            m.d.comb += self.op.eq(OpType.COMPARE)
        with m.Elif(self.match(_logic_encodings)):
            m.d.comb += self.op.eq(OpType.LOGIC)
        with m.Elif(self.match(_shift_encodings)):
            m.d.comb += self.op.eq(OpType.SHIFT)
        with m.Elif(self.match(_auipc_encodings)):
            m.d.comb += self.op.eq(OpType.AUIPC)
        with m.Elif(self.match(_lui_encodings)):
            m.d.comb += self.op.eq(OpType.LUI)
        with m.Elif(self.match(_jump_encodings)):
            m.d.comb += self.op.eq(OpType.JUMP)
        with m.Elif(self.match(_branch_encodings)):
            m.d.comb += self.op.eq(OpType.BRANCH)
        with m.Elif(self.match(_load_encodings)):
            m.d.comb += self.op.eq(OpType.LOAD)
        with m.Elif(self.match(_store_encodings)):
            m.d.comb += self.op.eq(OpType.STORE)
        with m.Elif(self.match(_ifence_encodings)):
            m.d.comb += self.op.eq(OpType.IFENCE)
        with m.Elif(self.match(_ecall_encodings)):
            m.d.comb += self.op.eq(OpType.ECALL)
        with m.Elif(self.match(_ebreak_encodings)):
            m.d.comb += self.op.eq(OpType.EBREAK)
        with m.Elif(self.match(_mret_encodings)):
            m.d.comb += self.op.eq(OpType.MRET)
        with m.Elif(self.match(_wfi_encodings)):
            m.d.comb += self.op.eq(OpType.WFI)
        with m.Elif(self.match(_csr_encodings)):
            m.d.comb += self.op.eq(OpType.CSR)

        # Illegal instruction detection

        m.d.comb += self.illegal.eq(self.op == OpType.UNKNOWN)

        return m
