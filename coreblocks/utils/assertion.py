from amaranth import *
from amaranth.tracer import get_src_loc
from functools import reduce
import operator
from dataclasses import dataclass
from transactron.utils import SrcLoc
from coreblocks.params import GenParams
from coreblocks.params.dependencies import DependencyManager, ListKey

__all__ = ["AssertKey", "assertion", "assert_bit", "assert_bits"]


@dataclass(frozen=True)
class AssertKey(ListKey[tuple[Value, SrcLoc]]):
    pass


def assertion(gen_params: GenParams, v: Value, *, src_loc_at: int = 0):
    src_loc = get_src_loc(1 + src_loc_at)
    gen_params.get(DependencyManager).add_dependency(AssertKey(), (v, src_loc))


def assert_bits(gen_params: GenParams) -> list[tuple[Value, SrcLoc]]:
    connections = gen_params.get(DependencyManager)
    return connections.get_dependency(AssertKey())


def assert_bit(gen_params: GenParams) -> Value:
    return reduce(operator.and_, assert_bits(gen_params), C(1))
