from enum import IntEnum, auto, unique
from typing import Iterable

from coreblocks.params import Extension


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
    SINGLE_BIT_MANIPULATION = auto()
    ADDRESS_GENERATION = auto()


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
        OpType.ADDRESS_GENERATION,
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
    Extension.ZBS: [
        OpType.SINGLE_BIT_MANIPULATION,
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
