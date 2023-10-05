import math
from itertools import takewhile

from amaranth.lib.enum import unique, Enum, IntEnum, IntFlag, auto
import enum

__all__ = [
    "InstrType",
    "Opcode",
    "Funct3",
    "Funct6",
    "Funct7",
    "Funct12",
    "ExceptionCause",
    "Extension",
    "FenceTarget",
    "FenceFm",
    "ISA",
    "RegisterType",
    "funct6_to_funct7",
    "load_store_width_to_eew",
    "SEW",
    "EEW",
    "EMUL",
    "LMUL",
    "eew_to_bits",
    "bits_to_eew",
    "eew_div_2",
    "lmul_to_float",
    "lmul_to_int",
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
    S1U = 6  # Unsigned imm in RS1
    S1I = 7  # Imm in RS1
    S1IS2 = 8  # Imm in RS1, valid RS2


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
    OP = 0b01100
    LUI = 0b01101
    OP32 = 0b01110
    OP_V = 0b10101
    BRANCH = 0b11000
    JALR = 0b11001
    JAL = 0b11011
    SYSTEM = 0b11100


class Funct3(IntEnum, shape=3):
    JALR = BEQ = B = ADD = SUB = FENCE = PRIV = MUL = MULW = _EINSTRACCESSFAULT = OPIVV = VMEM8 = 0b000
    BNE = H = SLL = FENCEI = CSRRW = MULH = BCLR = BINV = BSET = CLZ = CPOP = CTZ = ROL \
            = SEXTB = SEXTH = CLMUL = _EILLEGALINSTR = OPFVV = 0b001  # fmt: skip
    W = SLT = CSRRS = MULHSU = SH1ADD = CLMULR = _EBREAKPOINT = OPMVV = 0b010
    D = SLTU = CSRRC = MULHU = CLMULH = _EINSTRPAGEFAULT = OPIVI = 0b011
    BLT = BU = XOR = DIV = DIVW = SH2ADD = MIN = XNOR = ZEXTH = OPIVX = 0b100
    BGE = HU = SR = CSRRWI = DIVU = DIVUW = BEXT = ORCB = REV8 = ROR = MINU = OPFVF = VMEM16 = 0b101
    BLTU = OR = CSRRSI = REM = REMW = SH3ADD = MAX = ORN = OPMVX = VMEM32 = 0b110
    BGEU = AND = CSRRCI = REMU = REMUW = ANDN = MAXU = OPCFG = VMEM64 = 0b111


class Funct6(IntEnum, shape=6):
    VADD = 0b000000
    VSUB = 0b000010
    VRSUB = 0b000011
    VMINU = 0b000100
    VMIN = 0b000101
    VMAXU = 0b000110
    VMAX = 0b000111
    VAND = 0b001001
    VOR = 0b001010
    VXOR = 0b001011
    VRGATHER = 0b001100
    VSLIDEUP = VRGATHEREI16 = 0b001110
    VSLIDEDOWN = 0b001111
    VADC = 0b010000
    VMADC = 0b010001
    VSBC = 0b010010
    VMSBC = 0b010011
    VMERGE = VMV = 0b010111
    VMSEQ = 0b011000
    VMSNE = 0b011001
    VMSLTU = 0b011010
    VMSLT = 0b011011
    VMSLEU = 0b011100
    VMSLE = 0b011101
    VMSGTU = 0b011110
    VMSGT = 0b011111
    VSADDU = 0b100000
    VSADD = 0b100001
    VSSUBU = 0b100010
    VSSUB = 0b100011
    VSLL = 0b100101
    VSMUL = VMV1R = VMV2R = VMV4R = VMV8R = 0b100111
    VSRL = 0b101000
    VSRA = 0b101001
    VSSRL = 0b101010
    VSSRA = 0b101011
    VNSRL = 0b101100
    VNSRA = 0b101101
    VNCLIPU = 0b101110
    VNCLIP = 0b101111
    VWREDSUMU = 0b110000
    VWREDSUM = 0b110001


class Funct7(IntEnum, shape=7):
    SL = SLT = ADD = XOR = OR = AND = 0b0000000
    SA = SUB = ANDN = ORN = XNOR = 0b0100000
    MULDIV = 0b0000001
    SH1ADD = SH2ADD = SH3ADD = 0b0010000
    BCLR = BEXT = 0b0100100
    BINV = REV8 = 0b0110100
    BSET = ORCB = 0b0010100
    MAX = MIN = CLMUL = 0b0000101
    ROL = ROR = SEXTB = SEXTH = CPOP = CLZ = CTZ = 0b0110000
    ZEXTH = 0b0000100
    SFENCEVMA = 0b0001001


def funct6_to_funct7(funct6: Funct6, vm: bool | int) -> Funct7:
    return Funct7(int(funct6) * 2 + int(vm))


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
class RegisterType(IntEnum, shape=1):
    X = 0b0
    V = 0b1


@unique
class ExceptionCause(IntEnum, shape=4):
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


class SEW(IntEnum):
    """Representation of possible SEW

    This enum represents SEWs as defined by the V extension, that
    we are able to support in our core.

    Possible values are represented by the small integer numbers to
    compress the representation as much as possible. So it dosn't
    take much HW resources to represent an SEW.
    """

    w8 = 0
    w16 = 1
    w32 = 2
    w64 = 3


EEW = SEW


class LMUL(IntEnum):
    m1 = 0
    m2 = 1
    m4 = 2
    m8 = 3
    mf2 = 7  # multiply fractional 2 --> LMUL=1/2
    mf4 = 6
    mf8 = 5


EMUL = LMUL


def eew_to_bits(eew: EEW) -> int:
    """Convert EEW to number of bits

    This function takes an eew in the form of enum and converts it to an
    integer representing the width in bits of an element for the given eew.

    Parameters
    ----------
    eew : EEW
        EEW to convert to bit length.

    Returns
    -------
    width : int
        The width in bits of an element for the given eew.
    """
    if eew == EEW.w8:
        return 8
    elif eew == EEW.w16:
        return 16
    elif eew == EEW.w32:
        return 32
    elif eew == EEW.w64:
        return 64
    else:
        raise ValueError(f"Not known EEW: {eew}")


def bits_to_eew(bits: int) -> EEW:
    """Convert width in bits to EEW

    Parameters
    ----------
    bits : int
        The width of an element in bits.

    Returns
    -------
    eew : EEW
        EEW representing elements with the given width.
    """
    if bits == 8:
        return EEW.w8
    elif bits == 16:
        return EEW.w16
    elif bits == 32:
        return EEW.w32
    elif bits == 64:
        return EEW.w64
    else:
        raise ValueError(f"Not known EEW: {bits}")


def eew_div_2(eew: EEW) -> EEW:
    """Reduce EEW by 2

    This function is a shortcut to easily reduce the EEW width by a factor of 2.

    Parameters
    ----------
    eew : EEW
        EEW to be divided by 2.
    """
    return bits_to_eew(eew_to_bits(eew) // 2)


def lmul_to_float(lmul: LMUL) -> float:
    """Converts LMUL to float

    Parameters
    ----------
    lmul : LMUL
        The lmul to convert.

    Returns
    -------
    float
        The multiplier that is represented by `lmul`.
    """
    match lmul:
        case LMUL.m1:
            return 1
        case LMUL.m2:
            return 2
        case LMUL.m4:
            return 4
        case LMUL.m8:
            return 8
        case LMUL.mf2:
            return 0.5
        case LMUL.mf4:
            return 0.25
        case LMUL.mf8:
            return 0.125


def lmul_to_int(lmul: LMUL) -> int:
    """Convert LMUL to int by rounding up.

    Parameters
    ----------
    lmul : LMUL
        Value to convert.
    """
    return math.ceil(lmul_to_float(lmul))


def load_store_width_to_eew(funct3: Funct3 | int) -> EEW:
    """Convert vector load/store funct3 to EEW.

    Parameters
    ----------
    funct3 : Funct3 | int
        Value to convert.
    """
    match funct3:
        # constants taken from RISC-V V extension specification
        case 0:
            return EEW.w8
        case 5:
            return EEW.w16
        case 6:
            return EEW.w32
        case 7:
            return EEW.w64
    raise ValueError("Wrong vector load/store width.")


@unique
class Extension(enum.IntFlag):
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

# Extensions (not aliases) that only imply other sub-extensions, but don't add any new OpTypes.
extension_only_implies = {
    Extension.B,
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

        for ext, requirements in _extension_requirements.items():
            if ext in self.extensions and requirements not in self.extensions:
                for req in Extension:
                    if req in requirements and req not in self.extensions:
                        raise RuntimeError(
                            f"ISA extension {ext.name} requires the {req.name} extension to be supported"
                        )

        # I & E extensions can coexist if I extenstion can be disableable at runtime
        if self.extensions & Extension.E and not self.extensions & Extension.I:
            self.reg_cnt = 16
        else:
            self.reg_cnt = 32
        self.reg_cnt_log = self.reg_cnt.bit_length() - 1

        self.ilen = 32
        self.ilen_bytes = self.ilen // 8
        self.ilen_log = self.ilen.bit_length() - 1

        self.reg_field_bits = 5

        self.csr_alen = 12

        if self.extensions & Extension.V:
            self.v_zimmlen = 11
        else:
            self.v_zimmlen = 0


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
