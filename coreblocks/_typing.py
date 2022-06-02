from typing import List, Tuple, Type, Any
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import ValueCastable
from amaranth.hdl.rec import Direction, Layout

FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | int | range | Type[Enum]
LayoutLike = Layout | List[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]
