from collections.abc import Callable
from amaranth import *
from dataclasses import dataclass, field
from functools import partial
from coreblocks.params.dependencies import SimpleKey, UnifierKey
from coreblocks.transactions.core import Method, TModule
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.utils.protocols import Unifier


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
class InstructionPrecommitKey(UnifierKey):
    unifier: Callable[[list[Method]], Unifier] = field(
        default=precommit_unifier, init=False
    )


@dataclass(frozen=True)
class InstructionCommitKey(UnifierKey):
    unifier: Callable[[list[Method]], Unifier] = field(default=MethodProduct, init=False)


@dataclass(frozen=True)
class BranchResolvedKey(UnifierKey):
    unifier: Callable[[list[Method]], Unifier] = field(default=Collector, init=False)
