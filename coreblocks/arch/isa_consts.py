from amaranth.lib.enum import unique, Enum, IntEnum, IntFlag

__all__ = [
    "InstrType",
    "Opcode",
    "Funct3",
    "Funct7",
    "Funct12",
    "ExceptionCause",
    "FenceTarget",
    "FenceFm",
    "Registers",
    "PrivilegeLevel",
    "InterruptCauseNumber",
    "XlenEncoding",
]


@unique
class InstrType(Enum):
    R = 0
    I = 1  # noqa: E741
    S = 2
    B = 3
    U = 4
    J = 5


@unique
class Opcode(IntEnum, shape=5):
    LOAD = 0b00000
    LOAD_FP = 0b00001
    MISC_MEM = 0b00011
    OP_IMM = 0b00100
    AUIPC = 0b00101
    OP_IMM_32 = 0b00110
    STORE = 0b01000
    STORE_FP = 0b01001
    AMO = 0b01011
    OP = 0b01100
    LUI = 0b01101
    OP32 = 0b01110
    BRANCH = 0b11000
    JALR = 0b11001
    JAL = 0b11011
    SYSTEM = 0b11100
    RESERVED = 0b11111


class Funct3(IntEnum, shape=3):
    JALR = BEQ = B = ADD = SUB = FENCE = PRIV = MUL = MULW = _EINSTRACCESSFAULT = 0b000
    BNE = H = SLL = FENCEI = CSRRW = MULH = BCLR = BINV = BSET = CLZ = CPOP = CTZ = ROL \
            = SEXTB = SEXTH = CLMUL = _EILLEGALINSTR = 0b001  # fmt: skip
    W = SLT = CSRRS = MULHSU = SH1ADD = CLMULR = _EBREAKPOINT = 0b010
    D = SLTU = CSRRC = MULHU = CLMULH = _EINSTRPAGEFAULT = 0b011
    BLT = BU = XOR = DIV = DIVW = SH2ADD = MIN = XNOR = ZEXTH = 0b100
    BGE = HU = SR = CSRRWI = DIVU = DIVUW = BEXT = ORCB = REV8 = ROR = MINU = CZEROEQZ = 0b101
    BLTU = OR = CSRRSI = REM = REMW = SH3ADD = MAX = ORN = 0b110
    BGEU = AND = CSRRCI = REMU = REMUW = ANDN = MAXU = CZERONEZ = 0b111


class Funct7(IntEnum, shape=7):
    SL = SLT = ADD = XOR = OR = AND = AMOADD = 0b0000000
    MULDIV = 0b0000001
    ZEXTH = AMOSWAP = 0b0000100
    MAX = MIN = CLMUL = 0b0000101
    CZERO = 0b0000111
    LR = 0b0001000
    SFENCEVMA = 0b0001001
    SC = 0b0001100
    SH1ADD = SH2ADD = SH3ADD = AMOXOR = 0b0010000
    BSET = ORCB = 0b0010100
    SA = SUB = ANDN = ORN = XNOR = AMOOR = 0b0100000
    BCLR = BEXT = 0b0100100
    ROL = ROR = SEXTB = SEXTH = CPOP = CLZ = CTZ = AMOAND = 0b0110000
    BINV = REV8 = 0b0110100
    AMOMIN = 0b1000000
    AMOMAX = 0b1010000
    AMOMINU = 0b1100000
    AMOMAXU = 0b1110000


class Funct12(IntEnum, shape=12):
    ECALL = 0b000000000000
    EBREAK = 0b000000000001
    SRET = 0b000100000010
    MRET = 0b001100000010
    WFI = 0b000100000101
    CPOP = 0b011000000010
    CLZ = 0b011000000000
    CTZ = 0b011000000001
    ORCB = 0b001010000111
    REV8_32 = 0b011010011000
    REV8_64 = 0b011010111000
    SEXTB = 0b011000000100
    SEXTH = 0b011000000101
    ZEXTH = 0b000010000000


class Registers(IntEnum, shape=5):
    X0 = ZERO = 0b00000  # hardwired zero
    X1 = RA = 0b00001  # return address
    X2 = SP = 0b00010  # stack pointer
    X3 = GP = 0b00011  # global pointer
    X4 = TP = 0b00100  # thread pointer
    X5 = T0 = 0b00101  # temporary register 0
    X6 = T1 = 0b00110  # temporary register 1
    X7 = T2 = 0b00111  # temporary register 2
    X8 = S0 = FP = 0b01000  # saved register 0 / frame pointer
    X9 = S1 = 0b01001  # saved register 1
    X10 = A0 = 0b01010  # function argument 0 / return value 0
    X11 = A1 = 0b01011  # function argument 1 / return value 1
    X12 = A2 = 0b01100  # function argument 2
    X13 = A3 = 0b01101  # function argument 3
    X14 = A4 = 0b01110  # function argument 4
    X15 = A5 = 0b01111  # function argument 5
    X16 = A6 = 0b10000  # function argument 6
    X17 = A7 = 0b10001  # function argument 7
    X18 = S2 = 0b10010  # saved register 2
    X19 = S3 = 0b10011  # saved register 3
    X20 = S4 = 0b10100  # saved register 4
    X21 = S5 = 0b10101  # saved register 5
    X22 = S6 = 0b10110  # saved register 6
    X23 = S7 = 0b10111  # saved register 7
    X24 = S8 = 0b11000  # saved register 8
    X25 = S9 = 0b11001  # saved register 9
    X26 = S10 = 0b11010  # saved register 10
    X27 = S11 = 0b11011  # saved register 11
    X28 = T3 = 0b11100  # temporary register 3
    X29 = T4 = 0b11101  # temporary register 4
    X30 = T5 = 0b11110  # temporary register 5
    X31 = T6 = 0b11111  # temporary register 6


@unique
class FenceTarget(IntFlag, shape=4):
    MEM_W = 0b0001
    MEM_R = 0b0010
    DEV_O = 0b0100
    DEV_I = 0b1000


@unique
class FenceFm(IntEnum, shape=4):
    NONE = 0b0000
    TSO = 0b1000


@unique
class ExceptionCause(IntEnum, shape=5):
    INSTRUCTION_ADDRESS_MISALIGNED = 0
    INSTRUCTION_ACCESS_FAULT = 1
    ILLEGAL_INSTRUCTION = 2
    BREAKPOINT = 3
    LOAD_ADDRESS_MISALIGNED = 4
    LOAD_ACCESS_FAULT = 5
    STORE_ADDRESS_MISALIGNED = 6
    STORE_ACCESS_FAULT = 7
    ENVIRONMENT_CALL_FROM_U = 8
    ENVIRONMENT_CALL_FROM_S = 9
    ENVIRONMENT_CALL_FROM_M = 11
    INSTRUCTION_PAGE_FAULT = 12
    LOAD_PAGE_FAULT = 13
    STORE_PAGE_FAULT = 15
    _COREBLOCKS_ASYNC_INTERRUPT = 16
    _COREBLOCKS_MISPREDICTION = 17


@unique
class PrivilegeLevel(IntEnum, shape=2):
    USER = 0b00
    SUPERVISOR = 0b01
    MACHINE = 0b11


@unique
class TrapVectorMode(IntEnum, shape=2):
    DIRECT = 0b00
    VECTORED = 0b01


@unique
class InterruptCauseNumber(IntEnum):
    SSI = 1  # supervisor software interrupt
    MSI = 3  # machine software interrupt
    STI = 5  # supervisor timer interrupt
    MTI = 7  # machine timer interrupt
    SEI = 9  # supervisor external interrupt
    MEI = 11  # machine external interrupt


@unique
class XlenEncoding(IntEnum, shape=2):
    W32 = 1
    W64 = 2
    W128 = 3
