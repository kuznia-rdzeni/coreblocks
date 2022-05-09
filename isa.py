from enum import unique, Enum


__all__ = [
    "INSTR_LEN", "GPR_CNT", "GPR_WIDTH", "InstrType",
    "Opcode", "Funct3", "Funct7", "Funct12", "OpType"
]


INSTR_LEN = 32
GPR_CNT = 32
GPR_WIDTH = 32


@unique
class InstrType(Enum):
    R = 0
    I = 1
    S = 2
    B = 3
    U = 4
    J = 5


@unique
class Opcode(Enum):
    OP_IMM   = 0b00100
    LUI      = 0b01101
    AUIPC    = 0b00101
    OP       = 0b01100
    JAL      = 0b11011
    JALR     = 0b11001
    BRANCH   = 0b11000
    LOAD     = 0b00000
    STORE    = 0b01000
    MISC_MEM = 0b00011
    SYSTEM   = 0b11100


class Funct3(Enum):
    JALR = BEQ  = B       = ADD    = SUB    = FENCE  = PRIV = 0b000
    BNE  = H     = SLL    = FENCEI = CSRRW                  = 0b001
    W    = SLT   = CSRRS                                    = 0b010
    SLTU = CSRRC =                                          = 0b011
    BLT  = BU    = XOR                                      = 0b100
    BGE  = HU    = SR     = CSRRWI                          = 0b101
    BLTU = OR    = CSRRSI                                   = 0b110
    BGEU = AND   = CSRRCI                                   = 0b111


class Funct7(Enum):
    SL = SLT = ADD = XOR = OR = AND = 0b0000000
    SA = SUB                        = 0b0100000


class Funct12(Enum):
    ECALL  = 0b000000000000
    EBREAK = 0b000000000001
    MRET   = 0b001100000010
    WFI    = 0b000100000101


@unique
class OpType(Enum):
    UNKNOWN    = 0
    ARITHMETIC = 1
    COMPARE    = 2
    LOGIC      = 3
    SHIFT      = 4
    AUIPC      = 5
    LUI        = 6
    JUMP       = 7
    BRANCH     = 8
    LOAD       = 9
    STORE      = 10
    IFENCE     = 11
    ECALL      = 12
    EBREAK     = 13
    MRET       = 14
    WFI        = 15
    CSR        = 16
