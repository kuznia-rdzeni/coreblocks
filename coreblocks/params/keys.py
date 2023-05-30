from amaranth import *
from dataclasses import dataclass
from functools import partial
from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.core import TModule
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.peripherals.wishbone import WishboneMaster


__all__ = [
    "WishboneDataKey",
    "ROBSingleKey",
    "InstructionCommitKey",
    "InstructionPrecommitKey",
    "BranchResolvedKey",
]


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class ROBSingleKey(SimpleKey[Signal]):
    pass


@dataclass(frozen=True)
class InstructionPrecommitKey(UnifierKey, unifier=MethodProduct):
    pass


@dataclass(frozen=True)
class InstructionCommitKey(UnifierKey, unifier=MethodProduct):
    pass


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey, unifier=Collector):
    pass
