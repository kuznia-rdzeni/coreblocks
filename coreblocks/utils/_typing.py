from typing import Sequence, Tuple, Type, TypeAlias, Iterable, Mapping
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import Statement, ValueCastable
from amaranth.hdl.rec import Direction, Layout

# Types representing Amaranth concepts
FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | int | range | Type[Enum]
StatementLike: TypeAlias = Statement | Iterable["StatementLike"]
LayoutLike = Layout | Sequence[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]

# Internal Coreblocks types
DebugSignals: TypeAlias = Signal | Record | Iterable["DebugSignals"] | Mapping[str, "DebugSignals"]
LayoutList = list[Tuple[str, ShapeLike | "LayoutList"]]
