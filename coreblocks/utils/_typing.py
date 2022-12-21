from typing import Sequence, Tuple, Type, TypeVar, TypeGuard, Callable, Union, Any
from enum import Enum
from amaranth import *
from amaranth.hdl.ast import ValueCastable
from amaranth.hdl.rec import Direction, Layout
from inspect import signature

FragmentLike = Fragment | Elaboratable
ValueLike = Value | int | Enum | ValueCastable
ShapeLike = Shape | int | range | Type[Enum]
LayoutLike = Layout | Sequence[Tuple[str, ShapeLike | "LayoutLike"] | Tuple[str, ShapeLike | "LayoutLike", Direction]]

T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")


def is_one_arg_callable(func: Callable[[T1], T2] | Callable[[Any, Any], Any]) -> TypeGuard[Callable[[T1], T2]]:
    return len(signature(func).parameters) == 1


def is_two_arg_callable(func: Union[Callable[[Any], Any], Callable[[T1, T2], T3]]) -> TypeGuard[Callable[[T1, T2], T3]]:
    return len(signature(func).parameters) == 2
