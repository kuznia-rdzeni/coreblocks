from itertools import takewhile
from enum import unique, Enum, IntFlag


__all__ = ["InstrType", "Opcode", "Funct3", "Funct7", "Funct12", "OpType", "Extension", "ISA"]


@unique
class InstrType(Enum):
    R = 0
    I = 1  # noqa: E741
    S = 2
    B = 3
    U = 4
    J = 5


@unique
class Opcode(Enum):
    OP_IMM = 0b00100
    LUI = 0b01101
    AUIPC = 0b00101
    OP = 0b01100
    JAL = 0b11011
    JALR = 0b11001
    BRANCH = 0b11000
    LOAD = 0b00000
    STORE = 0b01000
    MISC_MEM = 0b00011
    SYSTEM = 0b11100


class Funct3(Enum):
    JALR = BEQ = B = ADD = SUB = FENCE = PRIV = 0b000
    BNE = H = SLL = FENCEI = CSRRW = 0b001
    W = SLT = CSRRS = 0b010
    SLTU = CSRRC = 0b011
    BLT = BU = XOR = 0b100
    BGE = HU = SR = CSRRWI = 0b101
    BLTU = OR = CSRRSI = 0b110
    BGEU = AND = CSRRCI = 0b111


class Funct7(Enum):
    SL = SLT = ADD = XOR = OR = AND = 0b0000000
    SA = SUB = 0b0100000


class Funct12(Enum):
    ECALL = 0b000000000000
    EBREAK = 0b000000000001
    MRET = 0b001100000010
    WFI = 0b000100000101


@unique
class OpType(Enum):
    UNKNOWN = 0
    ARITHMETIC = 1
    COMPARE = 2
    LOGIC = 3
    SHIFT = 4
    AUIPC = 5
    LUI = 6
    JUMP = 7
    BRANCH = 8
    LOAD = 9
    STORE = 10
    IFENCE = 11
    ECALL = 12
    EBREAK = 13
    MRET = 14
    WFI = 15
    CSR = 16


@unique
class Extension(IntFlag):
    E = 0x001
    I = 0x002  # noqa: E741
    M = 0x004
    A = 0x008
    F = 0x010
    D = 0x020
    C = 0x040
    ZICSR = 0x080
    ZIFENCE = 0x100


_extension_map = {
    "e": Extension.E,
    "i": Extension.I,
    "g": Extension.I
    | Extension.M
    | Extension.A
    | Extension.F
    | Extension.D
    | Extension.C
    | Extension.ZICSR
    | Extension.ZIFENCE,
    "m": Extension.M,
    "a": Extension.A,
    "f": Extension.F,
    "d": Extension.D,
    "c": Extension.C,
    "zicsr": Extension.ZICSR,
    "zifence": Extension.ZIFENCE,
}


class ISA:
    """
    ``ISA`` is a class that gathers all ISA-specific configurations.

    Parameters
    ----------
    isa_str: str
             String identifying a specific RISC-V ISA. Please refer to GCC's
             machine-dependent ``arch`` option for details.
    """

    def __init__(self, isa_str: str):
        if isa_str[0:2] != "rv":
            raise RuntimeError("Invalid ISA string " + isa_str)
        regwidth_str = "".join(takewhile(str.isdigit, isa_str[2:]))
        extensions_str = isa_str[len(regwidth_str) + 2 :]

        self.reg_width = int(regwidth_str)

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
                        raise RuntimeError("Unknown extension letter in ISA " "extensions string " + e)
                    parseExtension(e)

        if self.extensions & (Extension.E | Extension.I) == (Extension.E | Extension.I):
            raise RuntimeError("ISA extension string contains both E and I " "extensions")

        if self.extensions & Extension.E:
            self.reg_cnt = 16
        else:
            self.reg_cnt = self.reg_width

        if self.extensions & Extension.C:
            self.inst_width = 16
        else:
            self.inst_width = 32
