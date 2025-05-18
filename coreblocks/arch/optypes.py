from amaranth import *
from amaranth.lib.enum import unique, IntEnum, auto

from transactron.utils._typing import ValueLike

from .isa import Extension, extension_implications, extension_only_implies

__all__ = [
    "OpType",
    "CfiType",
]


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
    CSR_REG = auto()
    CSR_IMM = auto()
    MUL = auto()
    DIV_REM = auto()
    SINGLE_BIT_MANIPULATION = auto()
    ADDRESS_GENERATION = auto()
    BIT_MANIPULATION = auto()
    BIT_ROTATION = auto()
    UNARY_BIT_MANIPULATION_1 = auto()
    UNARY_BIT_MANIPULATION_2 = auto()
    UNARY_BIT_MANIPULATION_3 = auto()
    UNARY_BIT_MANIPULATION_4 = auto()
    UNARY_BIT_MANIPULATION_5 = auto()
    CLMUL = auto()
    SRET = auto()
    SFENCEVMA = auto()
    CZERO = auto()
    ATOMIC_MEMORY_OP = auto()
    ATOMIC_LR_SC = auto()
    #: Internal Coreblocks OpType, specifing that instruction caused Exception before FU execution
    EXCEPTION = auto()


@unique
class CfiType(IntEnum):
    """
    Types of control flow instructions.

    There are 4 main types: invalid, branch, JAL, and JALR. CALL and RET are
    just special cases of respectively JAL and JALR and thus the encoding
    was chosen in the way that it is sufficient to check the lowest two bits to
    get the main type and the third bit is just a hint about the specialized type.

    Because of these encoding tweaks, helper functions should be preferred to use
    to get the CFI type.
    """

    INVALID = 0b000  # Not a CFI
    BRANCH = 0b001

    JALR = 0b010  # Jump and Link Register
    RET = 0b110  # Return from a function (JALR with rs1 equal to x1 or x5)

    JAL = 0b011  # Jump and Link
    CALL = 0b111  # Call a function (JAL with rd equal to x1 or x5))

    @staticmethod
    def valid(val: ValueLike) -> Value:
        return Value.cast(val)[0:2] != CfiType.INVALID

    @staticmethod
    def is_branch(val: ValueLike) -> Value:
        return Value.cast(val)[0:2] == CfiType.BRANCH

    @staticmethod
    def is_jal(val: ValueLike) -> Value:
        return Value.cast(val)[0:2] == CfiType.JAL

    @staticmethod
    def is_jalr(val: ValueLike) -> Value:
        return Value.cast(val)[0:2] == CfiType.JALR


#
# Operation types grouped by extensions
# Note that this list provides 1:1 mappings and extension implications (like M->Zmmul) need to be resolved externally.
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
    ],
    Extension.ZIFENCEI: [
        OpType.FENCEI,
    ],
    Extension.ZICSR: [
        OpType.CSR_REG,
        OpType.CSR_IMM,
    ],
    Extension.ZMMUL: [
        OpType.MUL,
    ],
    Extension.M: [
        OpType.DIV_REM,
    ],
    Extension.ZAAMO: [
        OpType.ATOMIC_MEMORY_OP,
    ],
    Extension.ZALRSC: [
        OpType.ATOMIC_LR_SC,
    ],
    Extension.ZBS: [
        OpType.SINGLE_BIT_MANIPULATION,
    ],
    Extension.ZBA: [
        OpType.ADDRESS_GENERATION,
    ],
    Extension.ZBB: [
        OpType.BIT_MANIPULATION,
        OpType.BIT_ROTATION,
        OpType.UNARY_BIT_MANIPULATION_1,
        OpType.UNARY_BIT_MANIPULATION_2,
        OpType.UNARY_BIT_MANIPULATION_3,
        OpType.UNARY_BIT_MANIPULATION_4,
        OpType.UNARY_BIT_MANIPULATION_5,
    ],
    Extension.ZBC: [
        OpType.CLMUL,
    ],
    Extension.ZICOND: [
        OpType.CZERO,
    ],
    Extension.XINTMACHINEMODE: [
        OpType.MRET,
        OpType.WFI,
    ],
    Extension.XINTSUPERVISOR: [
        OpType.SRET,
        OpType.SFENCEVMA,
    ],
}


def optypes_required_by_extensions(
    extensions: Extension, resolve_implications=True, ignore_unsupported=False
) -> set[OpType]:
    optypes = set()

    if resolve_implications:
        implied_extensions = Extension(0)
        for ext in Extension:
            if ext in extensions:
                # check if extensions has implications, but skip if we don't have defined any optypes for it yet
                if ext in extension_implications and (ext in optypes_by_extensions or ext in extension_only_implies):
                    implied_extensions |= extension_implications[ext]
        extensions |= implied_extensions

    for ext in Extension:
        if ext in extensions:
            if ext in optypes_by_extensions:
                optypes = optypes.union(optypes_by_extensions[ext])
            elif not ignore_unsupported:
                raise Exception(f"Core does not support {ext!r} extension")

    return optypes
