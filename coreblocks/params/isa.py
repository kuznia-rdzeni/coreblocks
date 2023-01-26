from itertools import takewhile
from enum import unique, Enum, IntEnum, IntFlag, auto

__all__ = [
    "InstrType",
    "Opcode",
    "Funct3",
    "Funct7",
    "Funct12",
    "Extension",
    "FenceTarget",
    "FenceFm",
    "OpType",
    "optypes_by_extensions",
    "optypes_required_by_extensions",
    "ISA",
]

from typing import Iterable


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
    JALR = BEQ = B = ADD = SUB = FENCE = PRIV = MUL = MULW = 0b000
    BNE = H = SLL = FENCEI = CSRRW = MULH = 0b001
    W = SLT = CSRRS = MULHSU = 0b010
    SLTU = CSRRC = MULHU = 0b011
    BLT = BU = XOR = DIV = DIVW = 0b100
    BGE = HU = SR = CSRRWI = DIVU = DIVUW = 0b101
    BLTU = OR = CSRRSI = REM = REMW = 0b110
    BGEU = AND = CSRRCI = REMU = REMUW = 0b111


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
    """
    Enum of operation types. Do not confuse with Opcode.
    """

    UNKNOWN = auto()  # needs to be first
    ARITHMETIC = auto()
    COMPARE = auto()
    LOGIC = auto()
    SHIFT = auto()
    AUIPC = auto()
    JAL = auto()
    JALR = auto()
    BRANCH = auto()
    LOAD = auto()
    STORE = auto()
    FENCE = auto()
    ECALL = auto()
    EBREAK = auto()
    MRET = auto()
    WFI = auto()
    FENCEI = auto()
    CSR = auto()
    MUL = auto()
    DIV_REM = auto()


@unique
class Extension(IntFlag):
    """
    Enum of available RISC-V extensions.
    """

    #: Reduced integer operations
    E = auto()
    #: Full integer operations
    I = auto()  # noqa: E741
    #: Integer multiplication and division
    M = auto()
    #: Atomic operations
    A = auto()
    #: Single precision floating-point operations (32-bit)
    F = auto()
    #: Double precision floating-point operations (64-bit)
    D = auto()
    #: Quad precision floating-point operations (128-bit)
    Q = auto()
    #: Decimal floating-point operation
    L = auto()
    #: 16-bit compressed instructions
    C = auto()
    #: Bit manipulation operations
    B = auto()
    #: Dynamic languages
    J = auto()
    #: Transactional memory
    T = auto()
    #: Packed-SIMD extensions
    P = auto()
    #: Vector operations
    V = auto()
    #: User-level interruptions
    N = auto()
    #: Control and Status Register access
    ZICSR = auto()
    #: Instruction-Fetch fence operations
    ZIFENCEI = auto()
    #: Enables sending pause hint for energy saving
    ZIHINTPAUSE = auto()
    #: Enables non-temporal locality hints
    ZIHINTNTL = auto()
    #: Enables base counters and timers
    ZICNTR = auto()
    #: Enables hardware performance counters
    ZIHPM = auto()
    #: Misaligned atomic operations
    ZAM = auto()
    #: Half precision floating-point operations (16-bit)
    ZFH = auto()
    #: Minimal support for Half precision floating-point operations (16-bit)
    ZFHMIN = auto()
    #: Support for single precision floating-point operations in integer registers
    ZFINX = auto()
    #: Support for double precision floating-point operations in integer registers
    ZDINX = auto()
    #: Support for half precision floating-point operations in integer registers
    ZHINX = auto()
    #: Integer multiplication operations
    ZMMUL = auto()
    #: Extended shift operations
    ZBA = auto()
    #: Basic bit manipulation operations
    ZBB = auto()
    #: Carry-less multiplication operations
    ZBC = auto()
    #: Single bit operations
    ZBS = auto()
    #: Total store ordering
    ZTSO = auto()
    #: General extension containing all basic operations
    G = I | M | A | F | D | ZICSR | ZIFENCEI


# Mapping of names to corresponding extension
_extension_map = {e.name.lower(): e for e in Extension if e.name}

# Extensions which are mutually exclusive
_extension_exclusive = [
    [Extension.I, Extension.E],
]

# Extensions which explicitly require another extension in order to be valid (can be joined using | operator)
_extension_requirements = {
    Extension.D: Extension.F,
    Extension.Q: Extension.D,
    Extension.ZAM: Extension.A,
    Extension.ZFH: Extension.F,
    Extension.ZFHMIN: Extension.F,
    Extension.ZFINX: Extension.F,
    Extension.ZDINX: Extension.D,
    Extension.ZHINX: Extension.ZFH,
}

# Extensions which implicitly imply another extensions (can be joined using | operator)
_extension_implications = {
    Extension.F: Extension.ZICSR,
    Extension.M: Extension.ZMMUL,
    Extension.B: Extension.ZBA | Extension.ZBB | Extension.ZBC | Extension.ZBS,
}


#
# Operation types grouped by extensions
#

optypes_by_extensions = {
    Extension.I: [
        OpType.ARITHMETIC,
        OpType.COMPARE,
        OpType.LOGIC,
        OpType.SHIFT,
        OpType.AUIPC,
        OpType.JAL,
        OpType.JALR,
        OpType.BRANCH,
        OpType.LOAD,
        OpType.STORE,
        OpType.FENCE,
        OpType.ECALL,
        OpType.EBREAK,
        OpType.MRET,
        OpType.WFI,
    ],
    Extension.ZIFENCEI: [
        OpType.FENCEI,
    ],
    Extension.ZICSR: [
        OpType.CSR,
    ],
    Extension.M: [
        OpType.MUL,
        OpType.DIV_REM,
    ],
    Extension.ZMMUL: [
        OpType.MUL,
    ],
}


def optypes_required_by_extensions(extensions: Iterable[Extension]) -> set[OpType]:
    optypes = set()
    for ext in extensions:
        if ext in optypes_by_extensions:
            optypes = optypes.union(optypes_by_extensions[ext])
        else:
            raise Exception(f"Core do not support {ext} extension")
    return optypes


class ISA:
    """
    `ISA` is a class that gathers all ISA-specific configurations.

    For each of the numeric configuration value `val`, a corresponding
    `val_log` field is provided if relevant.

    Attributes
    ----------
    xlen : int
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
        """
        Parameters
        ----------
        isa_str : str
            String identifying a specific RISC-V ISA. Please refer to GCC's
            machine-dependent `arch` option for details.
        """
        isa_str = isa_str.lower()
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

        self.extensions = Extension(0)

        def parse_extension(e):
            val = _extension_map[e]
            if self.extensions & val:
                raise RuntimeError("Duplication in ISA extensions string")
            self.extensions |= val

        for es in extensions_str.split("_"):
            for i, e in enumerate(es):
                if e in _extension_map:
                    parse_extension(e)
                elif es[i:] in _extension_map:
                    parse_extension(es[i:])
                    break
                else:
                    raise RuntimeError(f"Neither {es[i]} nor {es[i:]} is a valid extension in {es}")

        if (self.extensions & Extension.E) and self.xlen != 32:
            raise RuntimeError("ISA extension E with XLEN != 32")

        for (ext, imply) in _extension_implications.items():
            if ext in self.extensions:
                self.extensions |= imply

        for exclusive in _extension_exclusive:
            for i in range(len(exclusive)):
                for j in range(i + 1, len(exclusive)):
                    if exclusive[i] | exclusive[j] in self.extensions:
                        raise RuntimeError(
                            f"ISA extensions {exclusive[i].name} and {exclusive[j].name} are mutually exclusive"
                        )

        for (ext, requirements) in _extension_requirements.items():
            if ext in self.extensions and requirements not in self.extensions:
                for req in Extension:
                    if req in requirements and req not in self.extensions:
                        raise RuntimeError(
                            f"ISA extension {ext.name} requires the {req.name} extension to be supported"
                        )

        if self.extensions & Extension.E:
            self.reg_cnt = 16
        else:
            self.reg_cnt = 32
        self.reg_cnt_log = self.reg_cnt.bit_length() - 1

        self.ilen = 32
        self.ilen_bytes = self.ilen // 8
        self.ilen_log = self.ilen.bit_length() - 1

        self.csr_alen = 12
