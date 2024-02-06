from amaranth import *
from amaranth.tracer import get_src_loc
from functools import reduce
import operator
from dataclasses import dataclass
from transactron.utils.depcache import DependentCache
from transactron.utils import SrcLoc
from transactron.utils.dependencies import DependencyContext, DependencyManager, ListKey

__all__ = ["AssertKey", "assertion", "assert_bit", "assert_bits"]


@dataclass(frozen=True)
class AssertKey(ListKey[tuple[Value, SrcLoc]]):
    pass


def assertion(value: Value, *, src_loc_at: int = 0):
    """Signal if assertion false.

    This function might help find some hardware bugs which might otherwise be
    hard to detect. If `value` is false, a hardware signal is generated, which
    can terminate a simulation, or turn on a warning LED on a board.

    Parameters
    ----------
    value : Value
        If the value of this Amaranth expression is false, the assertion will
        fail.
    src_loc_at : int, optional
        How many stack frames below to look for the source location, used to
        identify the failing assertion.
    """
    src_loc = get_src_loc(src_loc_at)
    dependencies = DependencyContext.get()
    dependencies.add_dependency(AssertKey(), (value, src_loc))


def assert_bits(dependencies: DependentCache | DependencyManager) -> list[tuple[Value, SrcLoc]]:
    """Gets assertion bits.

    This function returns all the assertion signals created by `assertion`,
    together with their source locations.

    Parameters
    ----------
    dependencies : DependentCache | DependencyManager
        The assertion feature uses the `DependencyManager` to store
        assertions. If `DependentCache` is passed instead, `DependencyManager`
        is requested from the cache.
    """
    if isinstance(dependencies, DependentCache):
        dependencies = dependencies.get(DependencyManager)
    return dependencies.get_dependency(AssertKey())


def assert_bit(dependencies: DependentCache | DependencyManager) -> Value:
    """Gets assertion bit.

    The signal returned by this function is false if and only if there exists
    a false signal among assertion bits created by `assertion`.

    Parameters
    ----------
    dependencies : DependentCache | DependencyManager
        The assertion feature uses the `DependencyManager` to store
        assertions. If `DependentCache` is passed instead, `DependencyManager`
        is requested from the cache.
    """
    return reduce(operator.and_, [a[0] for a in assert_bits(dependencies)], C(1))
