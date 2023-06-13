"""
This type stub file was generated by pyright.
"""

from enum import Enum
from typing import NoReturn, OrderedDict
from .ast import *
from coreblocks.utils import LayoutLike

__all__ = ["Direction", "DIR_NONE", "DIR_FANOUT", "DIR_FANIN", "Layout", "Record"]
Direction = Enum('Direction', ('NONE', 'FANOUT', 'FANIN'))
DIR_NONE = Direction.NONE
DIR_FANOUT = Direction.FANOUT
DIR_FANIN = Direction.FANIN
class Layout:
    fields: OrderedDict

    @staticmethod
    def cast(obj: LayoutLike, *, src_loc_at=...) -> Layout:
        ...
    
    def __init__(self, fields, *, src_loc_at=...) -> None:
        ...
    
    def __getitem__(self, item): # -> Layout:
        ...
    
    def __iter__(self): # -> Generator[tuple[Unknown, Unknown, Unknown], None, None]:
        ...
    
    def __eq__(self, other) -> bool:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Record(ValueCastable):
    name: str
    layout: Layout
    fields: OrderedDict

    @staticmethod
    def like(other: Record, *, name=..., name_suffix=..., src_loc_at=...) -> Record:
        ...
    
    def __init__(self, layout, *, name=..., fields=..., src_loc_at=...) -> None:
        ...

    def __bool__(self) -> NoReturn:
        ...

    def __invert__(self) -> Value:
        ...

    def __neg__(self) -> Value:
        ...

    def __add__(self, other: ValueLike) -> Value:
        ...

    def __radd__(self, other: ValueLike) -> Value:
        ...

    def __sub__(self, other: ValueLike) -> Value:
        ...

    def __rsub__(self, other: ValueLike) -> Value:
        ...

    def __mul__(self, other: ValueLike) -> Value:
        ...

    def __rmul__(self, other: ValueLike) -> Value:
        ...

    def __mod__(self, other: ValueLike) -> Value:
        ...

    def __rmod__(self, other: ValueLike) -> Value:
        ...

    def __floordiv__(self, other: ValueLike) -> Value:
        ...

    def __rfloordiv__(self, other: ValueLike) -> Value:
        ...

    def __lshift__(self, other: ValueLike) -> Value:
        ...

    def __rlshift__(self, other: ValueLike) -> Value:
        ...

    def __rshift__(self, other: ValueLike) -> Value:
        ...

    def __rrshift__(self, other: ValueLike) -> Value:
        ...

    def __and__(self, other: ValueLike) -> Value:
        ...

    def __rand__(self, other: ValueLike) -> Value:
        ...

    def __xor__(self, other: ValueLike) -> Value:
        ...

    def __rxor__(self, other: ValueLike) -> Value:
        ...

    def __or__(self, other: ValueLike) -> Value:
        ...

    def __ror__(self, other: ValueLike) -> Value:
        ...

    def __eq__(self, other: ValueLike) -> Value:
        ...

    def __ne__(self, other: ValueLike) -> Value:
        ...

    def __lt__(self, other: ValueLike) -> Value:
        ...

    def __le__(self, other: ValueLike) -> Value:
        ...

    def __gt__(self, other: ValueLike) -> Value:
        ...

    def __ge__(self, other: ValueLike) -> Value:
        ...

    def __abs__(self) -> Value:
        ...

    def as_unsigned(self) -> Value:
        ...

    def as_signed(self) -> Value:
        ...
    
    def bool(self) -> Value:
        ...

    def any(self) -> Value:
        ...

    def all(self) -> Value:
        ...

    def xor(self) -> Value:
        ...

    def implies(premise, conclusion: ValueLike) -> Value:
        ...

    def bit_select(self, offset: ValueLike, width: int) -> Value:
        ...

    def word_select(self, offset: ValueLike, width: int) -> Value:
        ...

    def matches(self, *patterns) -> Value:
        ...

    def shift_left(self, amount: int) -> Value:
        ...

    def shift_right(self, amount: int) -> Value:
        ...

    def rotate_left(self, amount: int) -> Value:
        ...

    def rotate_right(self, amount: int) -> Value:
        ...

    def eq(self, value: ValueLike) -> Assign:
        ...

    def __getattr__(self, name: str):
        ...
    
    def __getitem__(self, item: str | tuple | int | slice):
        ...
    
    @ValueCastable.lowermethod
    def as_value(self) -> Value:
        ...
    
    def __len__(self) -> int:
        ...
    
    def __repr__(self) -> str:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def connect(self, *subordinates, include=..., exclude=...):
        ...
    


