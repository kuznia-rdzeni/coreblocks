from typing import Union, List, Tuple, Type, Any
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import ValueCastable
from amaranth.hdl.rec import Direction, Layout

FragmentLike = Union[Fragment, Elaboratable]
ValueLike = Union[Value, int, Enum, ValueCastable]
ShapeLike = Union[Shape, int, range, Type[Enum]]
# TODO: recursive definition: LayoutLike instead of Any
LayoutLike = Union[
    Layout,
    List[
        Union[
            Tuple[str, Union[ShapeLike, Any]],
            Tuple[str, Union[ShapeLike, Any], Direction],
        ]
    ],
]
