from dataclasses import dataclass, field
from coreblocks.params.fu_params import SimpleKey, UnifierKey
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils.protocols import Unifier


__all__ = [
    "WishboneDataKey",
    "InstructionCommitKey",
    "BranchResolvedKey",
]


@dataclass(frozen=True)
class WishboneDataKey(SimpleKey[WishboneMaster]):
    pass


@dataclass(frozen=True)
class InstructionCommitKey(UnifierKey):
    unifier: type[Unifier] = field(default=MethodProduct, init=False)


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey):
    unifier: type[Unifier] = field(default=Collector, init=False)
