from amaranth import *
from dataclasses import dataclass
from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = [
    "WishboneDataKey",
    "InstructionCommitKey",
    "BranchResolvedKey",
]


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class ROBSingleKey(SimpleKey[Signal]):
    pass


@dataclass(frozen=True)
class InstructionCommitKey(UnifierKey, unifier=MethodProduct):
    pass


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey, unifier=Collector):
    pass
