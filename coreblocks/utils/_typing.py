from typing import Protocol, Sequence, Tuple, Type, TypeAlias, Iterable, Mapping, runtime_checkable
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import Statement, ValueCastable
from amaranth.hdl.rec import Direction, Layout

FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | int | range | Type[Enum]
StatementLike: TypeAlias = Statement | Iterable["StatementLike"]
LayoutLike = Layout | Sequence[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]
DebugSignals: TypeAlias = Signal | Record | Iterable["DebugSignals"] | Mapping[str, "DebugSignals"]


class HasElaborate(Protocol):
    def elaborate(self, platform) -> "HasElaborate":
        ...


@runtime_checkable
class HasDebugSignals(Protocol):
    def debug_signals(self) -> DebugSignals:
        ...
