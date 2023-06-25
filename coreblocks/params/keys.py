from dataclasses import dataclass
from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.lib import MethodTryProduct, Collector
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = [
    "WishboneDataKey",
    "InstructionPrecommitKey",
    "BranchResolvedKey",
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
