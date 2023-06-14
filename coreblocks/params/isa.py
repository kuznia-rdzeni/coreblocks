from itertools import takewhile
from enum import unique, Enum, IntFlag, auto

from amaranth.hdl.ast import Const, ValueCastable

__all__ = [
    "InstrType",
    "Opcode",
    "Funct3",
    "Funct7",
    "Funct12",
    "Extension",
    "FenceTarget",
    "FenceFm",
    "ISA",
    "Registers",
]


@unique
class InstrType(Enum):
    R = 0
    I = 1  # noqa: E741
    S = 2
    B = 3
    U = 4
    J = 5


class ValueCastableHack(int, ValueCastable):
    @ValueCastable.lowermethod
    def as_value(self):
        raise NotImplementedError("width information lost!")


class BitEnum(ValueCastableHack, Enum):
    """
    A helper class that defines Amaranth enums with a width
    """

    __width: int

    def __init_subclass__(cls, *, width, **kwargs):
        cls.__width = width

    @ValueCastable.lowermethod
    def as_value(self):
        return Const(self.value, self.__width)


@unique
class Opcode(BitEnum, width=5):
    LOAD = 0b00000
    LOAD_FP = 0b00001
    MISC_MEM = 0b00011
    OP_IMM = 0b00100
    AUIPC = 0b00101
    OP_IMM_32 = 0b00110
    STORE = 0b01000
    STORE_FP = 0b01001
    OP = 0b01100
    LUI = 0b01101
    OP32 = 0b01110
    BRANCH = 0b11000
    JALR = 0b11001
    JAL = 0b11011
    SYSTEM = 0b11100


class Funct3(BitEnum, width=3):
    JALR = BEQ = B = ADD = SUB = FENCE = PRIV = MUL = MULW = 0b000
    BNE = H = SLL = FENCEI = CSRRW = MULH = BCLR = BINV = BSET = CLMUL = 0b001
    W = SLT = CSRRS = MULHSU = SH1ADD = CLMULR = 0b010
    D = SLTU = CSRRC = MULHU = CLMULH = 0b011
    BLT = BU = XOR = DIV = DIVW = SH2ADD = 0b100
    BGE = HU = SR = CSRRWI = DIVU = DIVUW = BEXT = 0b101
    BLTU = OR = CSRRSI = REM = REMW = SH3ADD = 0b110
    BGEU = AND = CSRRCI = REMU = REMUW = 0b111


class Funct7(BitEnum, width=7):
    SL = SLT = ADD = XOR = OR = AND = 0b0000000
    SA = SUB = 0b0100000
    MULDIV = 0b0000001
    SH1ADD = SH2ADD = SH3ADD = 0b0010000
    BCLR = BEXT = 0b0100100
    BINV = 0b0110100
    BSET = 0b0010100
    CLMUL = 0b0000101
    SFENCEVMA = 0b0001001


class Funct12(BitEnum, width=12):
    ECALL = 0b000000000000
    EBREAK = 0b000000000001
    SRET = 0b000100000010
    MRET = 0b001100000010
    WFI = 0b000100000101


class Registers(BitEnum, width=5):
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
class FenceTarget(BitEnum, width=4):
    MEM_W = 0b0001
    MEM_R = 0b0010
    DEV_O = 0b0100
    DEV_I = 0b1000


@unique
class FenceFm(BitEnum, width=4):
    NONE = 0b0000
    TSO = 0b1000


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
    #: Coreblocks internal categorizing extension: Machine-Mode Privilieged Instructions
    XINTMACHINEMODE = auto()
    #: Coreblocks internal categorizing extension: Supervisor Instructions
    XINTSUPERVISOR = auto()
    #: General extension containing all basic operations
    G = I | M | A | F | D | ZICSR | ZIFENCEI


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
extension_implications = {
    Extension.F: Extension.ZICSR,
    Extension.M: Extension.ZMMUL,
    Extension.B: Extension.ZBA | Extension.ZBB | Extension.ZBC | Extension.ZBS,
}


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
            val = Extension[e.upper()]
            if self.extensions & val:
                raise RuntimeError("Duplication in ISA extensions string")
            self.extensions |= val

        for es in extensions_str.split("_"):
            for i, e in enumerate(es):
                try:
                    parse_extension(e)
                except KeyError:
                    try:
                        parse_extension(es[i:])
                    except KeyError:
                        raise RuntimeError(f"Neither {es[i]} nor {es[i:]} is a valid extension in {es}") from None
                    break

        if (self.extensions & Extension.E) and self.xlen != 32:
            raise RuntimeError("ISA extension E with XLEN != 32")

        for ext, imply in extension_implications.items():
            if ext in self.extensions:
                self.extensions |= imply

        for exclusive in _extension_exclusive:
            for i in range(len(exclusive)):
                for j in range(i + 1, len(exclusive)):
                    if exclusive[i] | exclusive[j] in self.extensions:
                        raise RuntimeError(
                            f"ISA extensions {exclusive[i].name} and {exclusive[j].name} are mutually exclusive"
                        )

        for ext, requirements in _extension_requirements.items():
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


def gen_isa_string(extensions: Extension, isa_xlen: int, *, skip_internal: bool = False) -> str:
    isa_str = "rv"

    isa_str += str(isa_xlen)

    # G extension alias should be defined first
    if Extension.G in extensions:
        isa_str += "g"
        extensions ^= Extension.G

    previous_multi_letter = False
    for ext in Extension:
        if ext in extensions:
            ext_name = str(ext.name).lower()

            if skip_internal and ext_name.startswith("xint"):
                continue

            if previous_multi_letter:
                isa_str += "_"
            previous_multi_letter = len(ext_name) > 1

            isa_str += ext_name

    return isa_str
