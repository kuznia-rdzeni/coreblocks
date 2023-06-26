from typing import (
    ContextManager,
    Generic,
    NoReturn,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Type,
    TypeAlias,
    Iterable,
    Mapping,
    TypeVar,
    runtime_checkable,
)
from enum import Enum
from amaranth import *
from amaranth.lib.data import View
from amaranth.hdl.ast import ShapeCastable, Statement, ValueCastable
from amaranth.hdl.dsl import _ModuleBuilderSubmodules, _ModuleBuilderDomainSet, _ModuleBuilderDomain, FSM
from amaranth.hdl.rec import Direction, Layout

# Types representing Amaranth concepts
FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | ShapeCastable | int | range | Type[Enum]
StatementLike: TypeAlias = Statement | Iterable["StatementLike"]
LayoutLike = Layout | Sequence[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]
SwitchKey: TypeAlias = str | int | Enum

# Internal Coreblocks types
SignalBundle: TypeAlias = Signal | Record | View | Iterable["SignalBundle"] | Mapping[str, "SignalBundle"]
LayoutList = list[Tuple[str, ShapeLike | "LayoutList"]]


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

    def If(self, cond: ValueLike) -> ContextManager[None]:  # noqa: N802
        ...

    def Elif(self, cond: ValueLike) -> ContextManager[None]:  # noqa: N802
        ...

    def Else(self) -> ContextManager[None]:  # noqa: N802
        ...

    def Switch(self, test: ValueLike) -> ContextManager[None]:  # noqa: N802
        ...

    def Case(self, *patterns: SwitchKey) -> ContextManager[None]:  # noqa: N802
        ...

    def Default(self) -> ContextManager[None]:  # noqa: N802
        ...

    def FSM(self, reset: Optional[str] = ..., domain: str = ..., name: str = ...) -> ContextManager[FSM]:  # noqa: N802
        ...

    def State(self, name: str) -> ContextManager[None]:  # noqa: N802
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
