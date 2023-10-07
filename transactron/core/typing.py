from amaranth import *
from typing import TypeAlias, TYPE_CHECKING, Callable, Mapping
from .._utils import Graph, GraphCC
from coreblocks.utils._typing import ValueLike, SignalBundle, HasElaborate, SwitchKey, ModuleLike, LayoutLike

if TYPE_CHECKING:
    from .transaction import Transaction
    from .relation_database import MethodMap

TransactionGraph: TypeAlias = Graph["Transaction"]
TransactionGraphCC: TypeAlias = GraphCC["Transaction"]
PriorityOrder: TypeAlias = dict["Transaction", int]
TransactionScheduler: TypeAlias = Callable[["MethodMap", TransactionGraph, TransactionGraphCC, PriorityOrder], Module]
RecordDict: TypeAlias = ValueLike | Mapping[str, "RecordDict"]
TransactionOrMethod: TypeAlias = Union["Transaction", "Method"]
