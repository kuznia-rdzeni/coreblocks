from typing import Sequence, Tuple, Type, TypeAlias, Iterable, Mapping
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import ValueCastable
from amaranth.hdl.rec import Direction, Layout

FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | int | range | Type[Enum]
LayoutLike = Layout | Sequence[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]
DebugSignals: TypeAlias = Signal | Record | Iterable["DebugSignals"] | Mapping[str, "DebugSignals"]
