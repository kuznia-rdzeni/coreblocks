from itertools import takewhile
from enum import unique, Enum, IntEnum, IntFlag


__all__ = [
    "InstrType",
    "Opcode",
    "Funct3",
    "Funct7",
    "Funct12",
    "OpType",
    "Extension",
    "FenceTarget",
    "FenceFm",
    "ISA",
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
class Opcode(IntEnum):
    OP_IMM = 0b00100
    LUI = 0b01101
    AUIPC = 0b00101
    OP = 0b01100
    OP32 = 0b01110
    JAL = 0b11011
    JALR = 0b11001
    BRANCH = 0b11000
    LOAD = 0b00000
    STORE = 0b01000
    MISC_MEM = 0b00011
    SYSTEM = 0b11100


class Funct3(IntEnum):
    JALR = BEQ = B = ADD = SUB = FENCE = PRIV = MUL = 0b000
    BNE = H = SLL = FENCEI = CSRRW = MULH = 0b001
    W = SLT = CSRRS = MULHSU = 0b010
    SLTU = CSRRC = MULHU = 0b011
    BLT = BU = XOR = DIV = 0b100
    BGE = HU = SR = CSRRWI = DIVU = 0b101
    BLTU = OR = CSRRSI = REM = 0b110
    BGEU = AND = CSRRCI = REMU = 0b111


class Funct7(IntEnum):
    SL = SLT = ADD = XOR = OR = AND = 0b0000000
    SA = SUB = 0b0100000
    MULDIV = 0b0000001


class Funct12(IntEnum):
    ECALL = 0b000000000000
    EBREAK = 0b000000000001
    MRET = 0b001100000010
    WFI = 0b000100000101


@unique
class FenceTarget(IntFlag):
    MEM_W = 0b0001
    MEM_R = 0b0010
    DEV_O = 0b0100
    DEV_I = 0b1000


@unique
class FenceFm(IntEnum):
    NONE = 0b0000
    TSO = 0b1000


@unique
class OpType(IntEnum):
    UNKNOWN = 0
    ARITHMETIC = 1
    COMPARE = 2
    LOGIC = 3
    SHIFT = 4
    AUIPC = 5
    JUMP = 6
    BRANCH = 7
    LOAD = 8
    STORE = 9
    FENCE = 10
    ECALL = 11
    EBREAK = 12
    MRET = 13
    WFI = 14
    FENCEI = 15
    CSR = 16
    MUL = 17
    DIV_REM = 18
    MUL_W = 19
    DIV_REM_W = 20


@unique
class Extension(IntFlag):
    E = 0x001
    I = 0x002  # noqa: E741
    M = 0x004
    A = 0x008
    F = 0x010
    D = 0x020
    C = 0x040
    ZIFENCEI = 0x080
    ZICSR = 0x100


_extension_map = {
    "e": Extension.E,
    "i": Extension.I,
    "g": Extension.I | Extension.M | Extension.A | Extension.F | Extension.D | Extension.ZICSR | Extension.ZIFENCEI,
    "m": Extension.M,
    "a": Extension.A,
    "f": Extension.F,
    "d": Extension.D,
    "c": Extension.C,
    "zicsr": Extension.ZICSR,
    "zifencei": Extension.ZIFENCEI,
}


class ISA:
    """
    ``ISA`` is a class that gathers all ISA-specific configurations.

    For each of the numeric configuration value ``val``, a corresponding
    ``val_log`` field is provided if relevant.

    Parameters
    ----------
    isa_str: str
             String identifying a specific RISC-V ISA. Please refer to GCC's
             machine-dependent ``arch`` option for details.

    Configuration constants
    ----------
    xlen:
        Native integer register width.
    reg_cnt:
        Number of integer registers.
    ilen:
        Maximum instruction length.
    csr_alen:
        CSR address width.
    extensions:
        All supported extensions in the form of a bitwise or of `Extension`.
    """

    def __init__(self, isa_str: str):
        if isa_str[0:2] != "rv":
            raise RuntimeError("Invalid ISA string " + isa_str)
        xlen_str = "".join(takewhile(str.isdigit, isa_str[2:]))
        extensions_str = isa_str[len(xlen_str) + 2 :]

        if not len(xlen_str):
            raise RuntimeError("Empty inative base integer ISA width string")

        self.xlen = int(xlen_str)
        self.xlen_log = self.xlen.bit_length() - 1

        if self.xlen not in [32, 64, 128]:
            raise RuntimeError("Invalid inative base integer ISA width %d" % self.xlen)

        if len(extensions_str) == 0:
            raise RuntimeError("Empty ISA extensions string")

        # The first extension letter must be one of "i", "e", or "g".
        if extensions_str[0] not in ["i", "e", "g"]:
            raise RuntimeError("Invalid first letter of ISA extensions string " + extensions_str[0])

        self.extensions = 0x0

        def parseExtension(e):
            val = _extension_map[e]
            if self.extensions & val:
                raise RuntimeError("Duplication in ISA extensions string")
            self.extensions |= val

        for es in extensions_str.split("_"):
            if es in _extension_map.keys():
                parseExtension(es)
            else:
                for e in es:
                    if e not in _extension_map.keys():
                        raise RuntimeError("Unknown extension letter in ISA extensions string " + e)
                    parseExtension(e)

        if self.extensions & (Extension.E | Extension.I) == (Extension.E | Extension.I):
            raise RuntimeError("ISA extension string contains both E and I extensions")

        if (self.extensions & Extension.E) and self.xlen != 32:
            raise RuntimeError("ISA extension E with XLEN != 32")

        if self.extensions & (Extension.F | Extension.D) == Extension.D:
            raise RuntimeError("ISA extension D requires the F extension to be supported")

        if self.extensions & Extension.E:
            self.reg_cnt = 16
        else:
            self.reg_cnt = 32
        self.reg_cnt_log = self.reg_cnt.bit_length() - 1

        self.ilen = 32
        self.ilen_bytes = self.ilen // 8
        self.ilen_log = self.ilen.bit_length() - 1

        self.csr_alen = 12
