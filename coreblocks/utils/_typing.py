from typing import Protocol, Sequence, Tuple, Type, TypeAlias, Iterable, Mapping, runtime_checkable
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import ShapeCastable, Statement, ValueCastable
from amaranth.hdl.rec import Direction, Layout

# Types representing Amaranth concepts
FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | ShapeCastable | int | range | Type[Enum]
StatementLike: TypeAlias = Statement | Iterable["StatementLike"]
LayoutLike = Layout | Sequence[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]
SwitchKey: TypeAlias = str | int | Enum

# Internal Coreblocks types
SignalBundle: TypeAlias = Signal | Record | Iterable["SignalBundle"] | Mapping[str, "SignalBundle"]
LayoutList = list[Tuple[str, ShapeLike | "LayoutList"]]


class HasElaborate(Protocol):
    def elaborate(self, platform) -> "HasElaborate":
        ...


@runtime_checkable
class HasDebugSignals(Protocol):
    def debug_signals(self) -> SignalBundle:
        ...
