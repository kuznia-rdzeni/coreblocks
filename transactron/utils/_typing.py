from typing import (
    Generic,
    NoReturn,
    Optional,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
    Union,
    Any,
)
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from enum import Enum
from amaranth import *
from amaranth.lib.data import View
from amaranth.hdl.ast import ShapeCastable, Statement, ValueCastable
from amaranth.hdl.dsl import _ModuleBuilderSubmodules, _ModuleBuilderDomainSet, _ModuleBuilderDomain, FSM
from amaranth.hdl.rec import Direction, Layout

# Types representing Amaranth concepts
FragmentLike: TypeAlias = Fragment | Elaboratable
ValueLike: TypeAlias = Value | int | Enum | ValueCastable
ShapeLike: TypeAlias = Shape | ShapeCastable | int | range | type[Enum]
StatementLike: TypeAlias = Statement | Iterable["StatementLike"]
LayoutLike: TypeAlias = (
    Layout | Sequence[tuple[str, "ShapeLike | LayoutLike"] | tuple[str, "ShapeLike | LayoutLike", Direction]]
)
SwitchKey: TypeAlias = str | int | Enum

# Internal Coreblocks types
SignalBundle: TypeAlias = Signal | Record | View | Iterable["SignalBundle"] | Mapping[str, "SignalBundle"]
LayoutListField: TypeAlias = tuple[str, "ShapeLike | LayoutList"]
LayoutList: TypeAlias = list[LayoutListField]

RecordIntDict: TypeAlias = Mapping[str, Union[int, "RecordIntDict"]]
RecordIntDictRet: TypeAlias = Mapping[str, Any]  # full typing hard to work with
RecordValueDict: TypeAlias = Mapping[str, Union[ValueLike, "RecordValueDict"]]


class _ModuleBuilderDomainsLike(Protocol):
    def __getattr__(self, name: str) -> _ModuleBuilderDomain:
        ...

    def __getitem__(self, name: str) -> _ModuleBuilderDomain:
        ...

    def __setattr__(self, name: str, value: _ModuleBuilderDomain) -> None:
        ...

    def __setitem__(self, name: str, value: _ModuleBuilderDomain) -> None:
        ...


_T_ModuleBuilderDomains = TypeVar("_T_ModuleBuilderDomains", bound=_ModuleBuilderDomainsLike)


class ModuleLike(Protocol, Generic[_T_ModuleBuilderDomains]):
    submodules: _ModuleBuilderSubmodules
    domains: _ModuleBuilderDomainSet
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
    ) -> AbstractContextManager[FSM]:
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
