from typing import (
    Callable,
    Concatenate,
    ParamSpec,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
    runtime_checkable,
    Union,
    Any,
)
from collections.abc import Iterable, Mapping
from amaranth import *
from amaranth.lib.data import StructLayout, View
from amaranth_types import *
from amaranth_types import _ModuleBuilderDomainsLike

__all__ = [
    "FragmentLike",
    "ValueLike",
    "ShapeLike",
    "StatementLike",
    "SwitchKey",
    "SrcLoc",
    "MethodLayout",
    "MethodStruct",
    "SignalBundle",
    "LayoutListField",
    "LayoutList",
    "LayoutIterable",
    "RecordIntDict",
    "RecordIntDictRet",
    "RecordValueDict",
    "RecordDict",
    "ROGraph",
    "Graph",
    "GraphCC",
    "_ModuleBuilderDomainsLike",
    "ModuleLike",
    "HasElaborate",
    "HasDebugSignals",
]

# Internal Coreblocks types
SignalBundle: TypeAlias = Signal | Record | View | Iterable["SignalBundle"] | Mapping[str, "SignalBundle"]
LayoutListField: TypeAlias = tuple[str, "ShapeLike | LayoutList"]
LayoutList: TypeAlias = list[LayoutListField]
LayoutIterable: TypeAlias = Iterable[LayoutListField]
MethodLayout: TypeAlias = StructLayout | LayoutIterable
MethodStruct: TypeAlias = "View[StructLayout]"

RecordIntDict: TypeAlias = Mapping[str, Union[int, "RecordIntDict"]]
RecordIntDictRet: TypeAlias = Mapping[str, Any]  # full typing hard to work with
RecordValueDict: TypeAlias = Mapping[str, Union[ValueLike, "RecordValueDict"]]
RecordDict: TypeAlias = ValueLike | Mapping[str, "RecordDict"]

T = TypeVar("T")
U = TypeVar("U")
P = ParamSpec("P")

ROGraph: TypeAlias = Mapping[T, Iterable[T]]
Graph: TypeAlias = dict[T, set[T]]
GraphCC: TypeAlias = set[T]


@runtime_checkable
class HasDebugSignals(Protocol):
    def debug_signals(self) -> SignalBundle: ...


def type_self_kwargs_as(as_func: Callable[Concatenate[Any, P], Any]):
    """
    Decorator used to annotate `**kwargs` type to be the same as named arguments from `as_func` method.

    Works only with methods with (self, **kwargs) signature. `self` parameter is also required in `as_func`.
    """

    def return_func(func: Callable[Concatenate[Any, ...], T]) -> Callable[Concatenate[Any, P], T]:
        return cast(Callable[Concatenate[Any, P], T], func)

    return return_func
