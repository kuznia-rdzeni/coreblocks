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


def precommit_combiner(m: TModule, vals: list[Record]):
    return {"stall": Cat(val.stall for val in vals).any()}


precommit_unifier = partial(MethodProduct, combiner=([("stall", 1)], precommit_combiner))


@dataclass(frozen=True)
class InstructionPrecommitKey(UnifierKey, unifier=precommit_unifier):
    pass


@dataclass(frozen=True)
class InstructionCommitKey(UnifierKey, unifier=MethodProduct):
    pass


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey, unifier=Collector):
    pass
