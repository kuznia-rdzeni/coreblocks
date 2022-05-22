"""
This type stub file was generated by pyright.
"""

from .ast import *

__all__ = ["Direction", "DIR_NONE", "DIR_FANOUT", "DIR_FANIN", "Layout", "Record"]
Direction = ...
DIR_NONE = ...
DIR_FANOUT = ...
DIR_FANIN = ...

class Layout:
    @staticmethod
    def cast(obj, *, src_loc_at=...): ...
    def __init__(self, fields, *, src_loc_at=...) -> None: ...
    def __getitem__(self, item): ...
    def __iter__(self): ...
    def __eq__(self, other) -> bool: ...
    def __repr__(self): ...

class Record(ValueCastable):
    @staticmethod
    def like(other, *, name=..., name_suffix=..., src_loc_at=...): ...
    def __init__(self, layout, *, name=..., fields=..., src_loc_at=...) -> None: ...
    def __getattr__(self, name): ...
    def __getitem__(self, item): ...
    @ValueCastable.lowermethod
    def as_value(self): ...
    def __len__(self): ...
    def __repr__(self): ...
    def shape(self): ...
    def connect(self, *subordinates, include=..., exclude=...): ...
