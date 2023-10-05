from dataclasses import dataclass
from typing import TYPE_CHECKING

from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.lib import MethodTryProduct, Collector, Method
from coreblocks.peripherals.wishbone import WishboneMaster

if TYPE_CHECKING:
    from coreblocks.structs_common.csr_generic import GenericCSRRegisters  # noqa: F401
    from coreblocks.lsu.vector_lsu import VectorLSU  # noqa: F401

__all__ = [
    "WishboneDataKey",
    "InstructionPrecommitKey",
    "BranchResolvedKey",
    "ExceptionReportKey",
    "GenericCSRRegistersKey",
    "ROBBlockInterruptsKey",
    "ROBPeekKey",
    "LSUReservedKey",
    "VectorFrontendInsertKey",
    "VectorVRFAccessKey",
    "VectorLSUKey",
    "VectorScoreboardKey",
]


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class InstructionPrecommitKey(UnifierKey, unifier=MethodTryProduct):
    pass


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey, unifier=Collector):
    pass


@dataclass(frozen=True)
class ExceptionReportKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class GenericCSRRegistersKey(SimpleKey["GenericCSRRegisters"]):
    pass


@dataclass(frozen=True)
class ROBBlockInterruptsKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class ROBPeekKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class LSUReservedKey(SimpleKey[tuple[Method, Method]]):
    pass


# TODO To remove after refactor
@dataclass(frozen=True)
class VectorFrontendInsertKey(SimpleKey[Method]):
    pass


# TODO To remove after refactor
@dataclass(frozen=True)
class VectorVRFAccessKey(SimpleKey[tuple[list[Method], list[Method], list[Method]]]):
    pass


# TODO To remove after refactor
@dataclass(frozen=True)
class VectorLSUKey(SimpleKey["VectorLSU"]):
    pass


# TODO To remove after refactor
@dataclass(frozen=True)
class VectorScoreboardKey(SimpleKey[tuple[Method, Method]]):
    pass
