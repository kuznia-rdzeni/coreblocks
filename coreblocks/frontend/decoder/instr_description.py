from dataclasses import KW_ONLY, dataclass
from typing import Optional

from coreblocks.arch import *


@dataclass(frozen=True)
class Encoding:
    """
    Class representing encoding of single RISC-V instruction.

    Parameters
    ----------
    opcode: Opcode
        Opcode of instruction.
    funct3: Optional[Funct3]
        Three bits function identifier. If not exists for instruction then `None`.
    funct7: Optional[Funct7]
        Seven bits function identifier. If not exists for instruction then `None`.
    funct12: Optional[Funct12]
        Twelve bits function identifier. If not exists for instruction then `None`.
    instr_type_override: Optional[InstrType]
        Specify `InstrType` used for decoding of register and immediate for single opcode.
        If set to `None` optype is determined from instrustion opcode, which is almost always correct.
    rd_zero: bool
        `rd` field is specifed as constant zero in instruction encoding. Other fields are decoded
        accordingly to `InstrType`. Default is False.
    rs1_zero: bool
        `rs1` field is specifed as constant zero in instruction encoding. Other fields are decoded
        accordingly to `InstrType`. Default is False.
    """

    opcode: Opcode
    funct3: Optional[Funct3] = None
    funct7: Optional[Funct7] = None
    funct12: Optional[Funct12] = None
    _ = KW_ONLY
    instr_type_override: Optional[InstrType] = None
    rd_zero: bool = False
    rs1_zero: bool = False


#
# Instructions grouped by Operation types
#

instructions_by_optype = {
    OpType.ARITHMETIC: [
        Encoding(Opcode.OP_IMM, Funct3.ADD),  # addi
        Encoding(Opcode.OP, Funct3.ADD, Funct7.ADD),  # add
        Encoding(Opcode.OP, Funct3.ADD, Funct7.SUB),  # sub
        Encoding(Opcode.LUI),  # lui
    ],
    OpType.COMPARE: [
        Encoding(Opcode.OP_IMM, Funct3.SLT),  # slti
        Encoding(Opcode.OP_IMM, Funct3.SLTU),  # sltiu
        Encoding(Opcode.OP, Funct3.SLT, Funct7.SLT),  # slt
        Encoding(Opcode.OP, Funct3.SLTU, Funct7.SLT),  # sltu
    ],
    OpType.LOGIC: [
        Encoding(Opcode.OP_IMM, Funct3.XOR),  # xori
        Encoding(Opcode.OP_IMM, Funct3.OR),  # ori
        Encoding(Opcode.OP_IMM, Funct3.AND),  # andi
        Encoding(Opcode.OP, Funct3.XOR, Funct7.XOR),  # xor
        Encoding(Opcode.OP, Funct3.OR, Funct7.OR),  # or
        Encoding(Opcode.OP, Funct3.AND, Funct7.AND),  # and
    ],
    OpType.SHIFT: [
        Encoding(Opcode.OP_IMM, Funct3.SLL, Funct7.SL),  # slli
        Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SL),  # srli
        Encoding(Opcode.OP_IMM, Funct3.SR, Funct7.SA),  # srai
        Encoding(Opcode.OP, Funct3.SLL, Funct7.SL),  # sll
        Encoding(Opcode.OP, Funct3.SR, Funct7.SL),  # srl
        Encoding(Opcode.OP, Funct3.SR, Funct7.SA),  # sra
    ],
    OpType.AUIPC: [
        Encoding(Opcode.AUIPC),  # auipc
    ],
    OpType.JAL: [
        Encoding(Opcode.JAL),  # jal
    ],
    OpType.JALR: [
        Encoding(Opcode.JALR, Funct3.JALR),  # jalr
    ],
    OpType.BRANCH: [
        Encoding(Opcode.BRANCH, Funct3.BEQ),  # beq
        Encoding(Opcode.BRANCH, Funct3.BNE),  # bne
        Encoding(Opcode.BRANCH, Funct3.BLT),  # blt
        Encoding(Opcode.BRANCH, Funct3.BGE),  # bge
        Encoding(Opcode.BRANCH, Funct3.BLTU),  # bltu
        Encoding(Opcode.BRANCH, Funct3.BGEU),  # bgeu
    ],
    OpType.LOAD: [
        Encoding(Opcode.LOAD, Funct3.B),  # lb
        Encoding(Opcode.LOAD, Funct3.BU),  # lbu
        Encoding(Opcode.LOAD, Funct3.H),  # lh
        Encoding(Opcode.LOAD, Funct3.HU),  # lhu
        Encoding(Opcode.LOAD, Funct3.W),  # lw
    ],
    OpType.STORE: [
        Encoding(Opcode.STORE, Funct3.B),  # sb
        Encoding(Opcode.STORE, Funct3.H),  # sh
        Encoding(Opcode.STORE, Funct3.W),  # sw
    ],
    OpType.FENCE: [
        Encoding(Opcode.MISC_MEM, Funct3.FENCE),  # fence
    ],
    OpType.ECALL: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.ECALL, rd_zero=True, rs1_zero=True),  # ecall
    ],
    OpType.EBREAK: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.EBREAK, rd_zero=True, rs1_zero=True),  # ebreak
    ],
    OpType.MRET: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.MRET, rd_zero=True, rs1_zero=True),  # mret
    ],
    OpType.WFI: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.WFI, rd_zero=True, rs1_zero=True),  # wfi
    ],
    OpType.FENCEI: [
        Encoding(Opcode.MISC_MEM, Funct3.FENCEI),  # fence.i
    ],
    OpType.CSR_REG: [
        Encoding(Opcode.SYSTEM, Funct3.CSRRW),  # csrrw
        Encoding(Opcode.SYSTEM, Funct3.CSRRS),  # csrrs
        Encoding(Opcode.SYSTEM, Funct3.CSRRC),  # csrrc
    ],
    OpType.CSR_IMM: [
        Encoding(Opcode.SYSTEM, Funct3.CSRRWI),  # csrrwi
        Encoding(Opcode.SYSTEM, Funct3.CSRRSI),  # csrrsi
        Encoding(Opcode.SYSTEM, Funct3.CSRRCI),  # csrrci
    ],
    OpType.MUL: [
        Encoding(Opcode.OP, Funct3.MUL, Funct7.MULDIV),  # mul
        Encoding(Opcode.OP, Funct3.MULH, Funct7.MULDIV),  # mulh
        Encoding(Opcode.OP, Funct3.MULHSU, Funct7.MULDIV),  # mulsu
        Encoding(Opcode.OP, Funct3.MULHU, Funct7.MULDIV),  # mulu
    ],
    OpType.DIV_REM: [
        Encoding(Opcode.OP, Funct3.DIV, Funct7.MULDIV),  # div
        Encoding(Opcode.OP, Funct3.DIVU, Funct7.MULDIV),  # divu
        Encoding(Opcode.OP, Funct3.REM, Funct7.MULDIV),  # rem
        Encoding(Opcode.OP, Funct3.REMU, Funct7.MULDIV),  # remu
    ],
    OpType.SINGLE_BIT_MANIPULATION: [
        Encoding(Opcode.OP, Funct3.BCLR, Funct7.BCLR),  # bclr
        Encoding(Opcode.OP_IMM, Funct3.BCLR, Funct7.BCLR),  # bclri
        Encoding(Opcode.OP, Funct3.BEXT, Funct7.BEXT),  # bext
        Encoding(Opcode.OP_IMM, Funct3.BEXT, Funct7.BEXT),  # bexti
        Encoding(Opcode.OP, Funct3.BSET, Funct7.BSET),  # bset
        Encoding(Opcode.OP_IMM, Funct3.BSET, Funct7.BSET),  # bseti
        Encoding(Opcode.OP, Funct3.BINV, Funct7.BINV),  # binv
        Encoding(Opcode.OP_IMM, Funct3.BINV, Funct7.BINV),  # binvi
    ],
    OpType.ADDRESS_GENERATION: [
        Encoding(Opcode.OP, Funct3.SH1ADD, Funct7.SH1ADD),
        Encoding(Opcode.OP, Funct3.SH2ADD, Funct7.SH2ADD),
        Encoding(Opcode.OP, Funct3.SH3ADD, Funct7.SH3ADD),
    ],
    OpType.BIT_MANIPULATION: [
        Encoding(Opcode.OP, Funct3.ANDN, Funct7.ANDN),
        Encoding(Opcode.OP, Funct3.MAX, Funct7.MAX),
        Encoding(Opcode.OP, Funct3.MAXU, Funct7.MAX),
        Encoding(Opcode.OP, Funct3.MIN, Funct7.MIN),
        Encoding(Opcode.OP, Funct3.MINU, Funct7.MIN),
        Encoding(Opcode.OP, Funct3.ORN, Funct7.ORN),
        Encoding(Opcode.OP, Funct3.XNOR, Funct7.XNOR),
    ],
    OpType.BIT_ROTATION: [
        Encoding(Opcode.OP, Funct3.ROL, Funct7.ROL),
        Encoding(Opcode.OP, Funct3.ROR, Funct7.ROR),
        Encoding(Opcode.OP_IMM, Funct3.ROR, Funct7.ROR),
    ],
    OpType.UNARY_BIT_MANIPULATION_1: [
        Encoding(Opcode.OP_IMM, Funct3.REV8, funct12=Funct12.REV8_32),
        Encoding(Opcode.OP_IMM, Funct3.SEXTB, funct12=Funct12.SEXTB),
        Encoding(Opcode.OP, Funct3.ZEXTH, funct12=Funct12.ZEXTH),
    ],
    # Instructions SEXTH, SEXTHB, CPOP, CLZ and CTZ cannot be distiguished by their Funct7 code
    # ORCB is here because of optimization to not lookup Funct7 in UNARY_BIT_MANIPULATION_1
    OpType.UNARY_BIT_MANIPULATION_2: [
        Encoding(Opcode.OP_IMM, Funct3.SEXTH, funct12=Funct12.SEXTH),
        Encoding(Opcode.OP_IMM, Funct3.ORCB, funct12=Funct12.ORCB),
    ],
    OpType.UNARY_BIT_MANIPULATION_3: [
        Encoding(Opcode.OP_IMM, Funct3.CLZ, funct12=Funct12.CLZ),
    ],
    OpType.UNARY_BIT_MANIPULATION_4: [
        Encoding(Opcode.OP_IMM, Funct3.CTZ, funct12=Funct12.CTZ),
    ],
    OpType.UNARY_BIT_MANIPULATION_5: [
        Encoding(Opcode.OP_IMM, Funct3.CPOP, funct12=Funct12.CPOP),
    ],
    OpType.CLMUL: [
        Encoding(Opcode.OP, Funct3.CLMUL, Funct7.CLMUL),
        Encoding(Opcode.OP, Funct3.CLMULH, Funct7.CLMUL),
        Encoding(Opcode.OP, Funct3.CLMULR, Funct7.CLMUL),
    ],
    OpType.SRET: [
        Encoding(Opcode.SYSTEM, Funct3.PRIV, funct12=Funct12.SRET, rd_zero=True, rs1_zero=True),  # sret
    ],
    OpType.SFENCEVMA: [
        Encoding(
            Opcode.SYSTEM, Funct3.PRIV, Funct7.SFENCEVMA, rd_zero=True, instr_type_override=InstrType.R
        ),  # sfence.vma
    ],
    OpType.CZERO: [
        Encoding(Opcode.OP, Funct3.CZEROEQZ, Funct7.CZERO),
        Encoding(Opcode.OP, Funct3.CZERONEZ, Funct7.CZERO),
    ],
    OpType.ATOMIC_MEMORY_OP: [
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOSWAP),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOADD),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOAND),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOOR),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOXOR),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOMAXU),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOMINU),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOMAX),
        Encoding(Opcode.AMO, Funct3.W, Funct7.AMOMIN),
    ],
    OpType.ATOMIC_LR_SC: [
        Encoding(Opcode.AMO, Funct3.W, Funct7.LR),
        Encoding(Opcode.AMO, Funct3.W, Funct7.SC),
    ],
}
