from dataclasses import dataclass
from typing import TYPE_CHECKING

from transactron.lib.dependencies import SimpleKey, UnifierKey
from transactron import Method
from transactron.lib import MethodTryProduct, Collector
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from amaranth import Signal

if TYPE_CHECKING:
    from coreblocks.structs_common.csr_generic import GenericCSRRegisters  # noqa: F401

__all__ = [
    "CommonBusDataKey",
    "InstructionPrecommitKey",
    "BranchResolvedKey",
    "ExceptionReportKey",
    "GenericCSRRegistersKey",
    "AsyncInterruptInsertSignalKey",
    "MretKey",
]


@dataclass(frozen=True)
class CommonBusDataKey(SimpleKey[BusMasterInterface]):
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
class AsyncInterruptInsertSignalKey(SimpleKey[Signal]):
    pass


@dataclass(frozen=True)
class MretKey(SimpleKey[Method]):
    pass
