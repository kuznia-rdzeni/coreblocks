from dataclasses import dataclass
from typing import TYPE_CHECKING

from transactron.lib.dependencies import SimpleKey, ListKey
from transactron import Method
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from amaranth import Signal

if TYPE_CHECKING:
    from coreblocks.priv.csr.csr_instances import GenericCSRRegisters  # noqa: F401
    from coreblocks.priv.csr.csr_register import CSRRegister  # noqa: F401

__all__ = [
    "CommonBusDataKey",
    "InstructionPrecommitKey",
    "MispredictionReportKey",
    "PredictedJumpTargetKey",
    "FetchResumeKey",
    "ExceptionReportKey",
    "GenericCSRRegistersKey",
    "AsyncInterruptInsertSignalKey",
    "MretKey",
    "CoreStateKey",
    "CSRListKey",
    "FlushICacheKey",
]


@dataclass(frozen=True)
class CommonBusDataKey(SimpleKey[BusMasterInterface]):
    pass


@dataclass(frozen=True)
class InstructionPrecommitKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class PredictedJumpTargetKey(SimpleKey[tuple[Method, Method]]):
    pass


@dataclass(frozen=True)
class FetchResumeKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class ExceptionReportKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class MispredictionReportKey(SimpleKey[Method]):
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


@dataclass(frozen=True)
class CoreStateKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class CSRListKey(ListKey["CSRRegister"]):
    """DependencyManager key collecting CSR registers globally as a list."""

    pass


@dataclass(frozen=True)
class FlushICacheKey(SimpleKey[Method]):
    pass
