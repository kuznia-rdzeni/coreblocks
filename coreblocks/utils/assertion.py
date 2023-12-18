from amaranth import *
from amaranth.tracer import get_src_loc
from functools import reduce
import operator
from dataclasses import dataclass
from coreblocks.params.genparams import DependentCache
from transactron.utils import SrcLoc
from coreblocks.params.dependencies import DependencyManager, ListKey

__all__ = ["AssertKey", "assertion", "assert_bit", "assert_bits"]


@dataclass(frozen=True)
class AssertKey(ListKey[tuple[Value, SrcLoc]]):
    pass


def assertion(dependencies: DependentCache | DependencyManager, v: Value, *, src_loc_at: int = 0):
    if isinstance(dependencies, DependentCache):
        dependencies = dependencies.get(DependencyManager)
    src_loc = get_src_loc(1 + src_loc_at)
    dependencies.add_dependency(AssertKey(), (v, src_loc))


def assert_bits(dependencies: DependentCache | DependencyManager) -> list[tuple[Value, SrcLoc]]:
    if isinstance(dependencies, DependentCache):
        dependencies = dependencies.get(DependencyManager)
    return dependencies.get_dependency(AssertKey())


def assert_bit(dependencies: DependentCache | DependencyManager) -> Value:
    return reduce(operator.and_, [a[0] for a in assert_bits(dependencies)], C(1))
