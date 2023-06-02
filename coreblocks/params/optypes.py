from enum import IntEnum, auto, unique

from coreblocks.params import Extension
from coreblocks.params.isa import extension_implications


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
    SRET = auto()


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
    Extension.ZBS: [
        OpType.SINGLE_BIT_MANIPULATION,
    ],
    Extension.ZBA: [
        OpType.ADDRESS_GENERATION,
    ],
    Extension.XINTMACHINEMODE: [
        OpType.ECALL,
        OpType.EBREAK,
        OpType.MRET,
        OpType.WFI,
    ],
    Extension.XINTSUPERVISOR: [
        OpType.SRET,
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
                if ext in extension_implications and ext in optypes_by_extensions:
                    implied_extensions |= extension_implications[ext]
        extensions |= implied_extensions

    for ext in Extension:
        if ext in extensions:
            if ext in optypes_by_extensions:
                optypes = optypes.union(optypes_by_extensions[ext])
            elif not ignore_unsupported:
                raise Exception(f"Core does not support {ext!r} extension")

    return optypes
