from amaranth import *
from typing import TypeAlias, TYPE_CHECKING, Callable, Mapping, Union

# Proxy imports before cleaning transactron and coreblocks dependencies
from coreblocks.utils._typing import ValueLike, SignalBundle, HasElaborate, SwitchKey  # noqa: F401
from coreblocks.utils._typing import ModuleLike, LayoutLike  # noqa: F401

if TYPE_CHECKING:
    from .transaction import Transaction
    from .method import Method
    from .manager import MethodMap
    from .._utils import Graph, GraphCC

__all__ = [
    "RecordDict",
    "MethodLayout",
]

TransactionGraph: TypeAlias = "Graph[Transaction]"
TransactionGraphCC: TypeAlias = "GraphCC[Transaction]"
PriorityOrder: TypeAlias = dict["Transaction", int]
TransactionScheduler: TypeAlias = Callable[["MethodMap", TransactionGraph, TransactionGraphCC, PriorityOrder], Module]
RecordDict: TypeAlias = ValueLike | Mapping[str, "RecordDict"]
TransactionOrMethod: TypeAlias = Union["Transaction", "Method"]
MethodLayout: TypeAlias = LayoutLike
