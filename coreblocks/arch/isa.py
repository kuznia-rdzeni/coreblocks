from itertools import takewhile

from amaranth.lib.enum import unique, auto
import enum

__all__ = [
    "Extension",
    "ISA",
]


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
    #: Integer conditional operations
    ZICOND = auto()
    #: Atomic memory operations
    ZAAMO = auto()
    #: Load-Reserved/Store-Conditional Instructions
    ZALRSC = auto()
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
    Extension.A: Extension.ZAAMO | Extension.ZALRSC,
    Extension.B: Extension.ZBA | Extension.ZBB | Extension.ZBC | Extension.ZBS,
}

# Extensions (not aliases) that only imply other sub-extensions, but don't add any new OpTypes.
extension_only_implies = {
    Extension.A,
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
