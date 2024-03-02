from typing import (
    Callable,
    Concatenate,
    Generic,
    NoReturn,
    Optional,
    ParamSpec,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
    runtime_checkable,
    Union,
    Any,
    TYPE_CHECKING,
)
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from enum import Enum
from amaranth import *
from amaranth.lib.data import StructLayout, View
from amaranth.hdl import ShapeCastable, ValueCastable
from amaranth.hdl.rec import Direction, Layout

if TYPE_CHECKING:
    from amaranth.hdl._ast import Statement
    from amaranth.hdl._dsl import _ModuleBuilderSubmodules, _ModuleBuilderDomainSet, _ModuleBuilderDomain
    import amaranth.hdl._dsl

__all__ = [
    "FragmentLike",
    "ValueLike",
    "ShapeLike",
    "StatementLike",
    "LayoutLike",
    "SwitchKey",
    "SrcLoc",
    "MethodLayout",
    "MethodStruct",
    "SrcLoc",
    "SignalBundle",
    "LayoutListField",
    "LayoutList",
    "LayoutIterable",
    "RecordIntDict",
    "RecordIntDictRet",
    "RecordValueDict",
    "ROGraph",
    "Graph",
    "GraphCC",
    "_ModuleBuilderDomainsLike",
    "ModuleLike",
    "HasElaborate",
    "HasDebugSignals",
]

# Types representing Amaranth concepts
FragmentLike: TypeAlias = Fragment | Elaboratable
ValueLike: TypeAlias = Value | int | Enum | ValueCastable
ShapeLike: TypeAlias = Shape | ShapeCastable | int | range | type[Enum]
StatementLike: TypeAlias = Union["Statement", Iterable["StatementLike"]]
LayoutLike: TypeAlias = (
    Layout | Sequence[tuple[str, "ShapeLike | LayoutLike"] | tuple[str, "ShapeLike | LayoutLike", Direction]]
)
SwitchKey: TypeAlias = str | int | Enum
SrcLoc: TypeAlias = tuple[str, int]

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

T = TypeVar("T")
U = TypeVar("U")
P = ParamSpec("P")

ROGraph: TypeAlias = Mapping[T, Iterable[T]]
Graph: TypeAlias = dict[T, set[T]]
GraphCC: TypeAlias = set[T]


class _ModuleBuilderDomainsLike(Protocol):
    def __getattr__(self, name: str) -> "_ModuleBuilderDomain":
        ...

    def __getitem__(self, name: str) -> "_ModuleBuilderDomain":
        ...

    def __setattr__(self, name: str, value: "_ModuleBuilderDomain") -> None:
        ...

    def __setitem__(self, name: str, value: "_ModuleBuilderDomain") -> None:
        ...


_T_ModuleBuilderDomains = TypeVar("_T_ModuleBuilderDomains", bound=_ModuleBuilderDomainsLike)


class ModuleLike(Protocol, Generic[_T_ModuleBuilderDomains]):
    submodules: "_ModuleBuilderSubmodules"
    domains: "_ModuleBuilderDomainSet"
    d: _T_ModuleBuilderDomains

    def If(self, cond: ValueLike) -> AbstractContextManager[None]:  # noqa: N802
        ...

    def Elif(self, cond: ValueLike) -> AbstractContextManager[None]:  # noqa: N802
        ...

    def Else(self) -> AbstractContextManager[None]:  # noqa: N802
        ...

    def Switch(self, test: ValueLike) -> AbstractContextManager[None]:  # noqa: N802
        ...

    def Case(self, *patterns: SwitchKey) -> AbstractContextManager[None]:  # noqa: N802
        ...

    def Default(self) -> AbstractContextManager[None]:  # noqa: N802
        ...

    def FSM(  # noqa: N802
        self, reset: Optional[str] = ..., domain: str = ..., name: str = ...
    ) -> AbstractContextManager["amaranth.hdl._dsl.FSM"]:
        ...

    def State(self, name: str) -> AbstractContextManager[None]:  # noqa: N802
        ...

    @property
    def next(self) -> NoReturn:
        ...

    @next.setter
    def next(self, name: str) -> None:
        ...


class HasElaborate(Protocol):
    def elaborate(self, platform) -> "HasElaborate":
        ...


@runtime_checkable
class HasDebugSignals(Protocol):
    def debug_signals(self) -> SignalBundle:
        ...


def type_self_kwargs_as(as_func: Callable[Concatenate[Any, P], Any]):
    """
    Decorator used to annotate `**kwargs` type to be the same as named arguments from `as_func` method.

    Works only with methods with (self, **kwargs) signature. `self` parameter is also required in `as_func`.
    """

    def return_func(func: Callable[Concatenate[Any, ...], T]) -> Callable[Concatenate[Any, P], T]:
        return cast(Callable[Concatenate[Any, P], T], func)

    return return_func
