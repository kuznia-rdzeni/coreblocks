from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Concatenate

from transactron.utils import MethodStruct
from transactron.lib.dependencies import SimpleKey, ListKey
from transactron import Method, TModule
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from amaranth import Signal

if TYPE_CHECKING:
    from coreblocks.priv.csr.csr_instances import GenericCSRRegisters  # noqa: F401
    from coreblocks.priv.csr.csr_register import CSRRegister  # noqa: F401

__all__ = [
    "CommonBusDataKey",
    "InstructionPrecommitKey",
    "BranchVerifyKey",
    "PredictedJumpTargetKey",
    "UnsafeInstructionResolvedKey",
    "ExceptionReportKey",
    "CSRInstancesKey",
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
class BranchVerifyKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class PredictedJumpTargetKey(SimpleKey[tuple[Method, Method]]):
    pass


@dataclass(frozen=True)
class UnsafeInstructionResolvedKey(SimpleKey[Method]):
    """
    Represents a method that is called by functional units when
    an unsafe instruction is executed and the core should be resumed.
    """

    pass


@dataclass(frozen=True)
class ExceptionReportKey(SimpleKey[Callable[[], Callable[Concatenate[TModule, ...], MethodStruct]]]):
    """
    Used to report exception details to the `ExceptionInformationRegister`.
    Needs to be called once in the component's constructor. The callable
    returned acts like a method call and can be used multiple times
    in `elaborate`.
    """

    pass


@dataclass(frozen=True)
class CSRInstancesKey(SimpleKey["GenericCSRRegisters"]):
    pass


@dataclass(frozen=True)
class AsyncInterruptInsertSignalKey(SimpleKey[Signal]):
    pass


@dataclass(frozen=True)
class WaitForInterruptResumeKey(SimpleKey[Signal]):
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
