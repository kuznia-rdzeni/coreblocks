from amaranth import *
from functools import reduce
import operator
from dataclasses import dataclass
from coreblocks.params import GenParams
from coreblocks.params.dependencies import DependencyManager, ListKey

__all__ = ["AssertKey", "assertion"]


@dataclass(frozen=True)
class AssertKey(ListKey[Value]):
    pass


def assertion(gen_params: GenParams, v: Value):
    gen_params.get(DependencyManager).add_dependency(AssertKey(), v)


def assert_bit(gen_params: GenParams) -> Value:
    connections = gen_params.get(DependencyManager)
    return reduce(operator.or_, connections.get_dependency(AssertKey()))
