from dataclasses import dataclass
from typing import TYPE_CHECKING
from amaranth import Signal

from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.lib import MethodTryProduct, Collector, Method
from coreblocks.peripherals.wishbone import WishboneMaster

if TYPE_CHECKING:
    from coreblocks.structs_common.csr_generic import GenericCSRRegisters  # noqa: F401

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

@dataclass(frozen = True)
class LSUReservedKey(SimpleKey[tuple[Method,Method]]):
    pass

# TODO rework vector core so that this key wouldn't be needed
@dataclass(frozen = True)
class VectorFrontendInsertKey(SimpleKey[Method]):
    pass

# TODO This also should be refactored
@dataclass(frozen = True)
class VectorVRFAccessKey(SimpleKey[tuple[list[Method], list[Method], list[Method]]]):
    pass
