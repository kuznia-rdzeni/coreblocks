from dataclasses import dataclass
from typing import TYPE_CHECKING

from coreblocks.params.dependencies import SimpleKey, UnifierKey
from transactron import Method
from transactron.lib import MethodProduct, MethodTryProduct
from coreblocks.peripherals.wishbone import WishboneMaster

if TYPE_CHECKING:
    from coreblocks.structs_common.csr_generic import GenericCSRRegisters  # noqa: F401

__all__ = [
    "WishboneDataKey",
    "InstructionPrecommitKey",
    "MretKey",
    "BranchResolvedKey",
    "ExceptionReportKey",
    "GenericCSRRegistersKey",
    "ClearKey",
]


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class InstructionPrecommitKey(UnifierKey, unifier=MethodTryProduct):
    pass


@dataclass(frozen=True)
class MretKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class BranchResolvedKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class ClearKey(UnifierKey, unifier=MethodProduct):
    pass


@dataclass(frozen=True)
class ExceptionReportKey(SimpleKey[Method]):
    pass


@dataclass(frozen=True)
class GenericCSRRegistersKey(SimpleKey["GenericCSRRegisters"]):
    pass
