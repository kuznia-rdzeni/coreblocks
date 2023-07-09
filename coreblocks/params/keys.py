from dataclasses import dataclass
from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.lib import MethodProduct, Method
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = [
    "WishboneDataKey",
    "InstructionPrecommitKey",
    "MretKey",
    "BranchResolvedKey",
    "ClearKey",
]


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class InstructionPrecommitKey(UnifierKey, unifier=MethodProduct):
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
