"""
This type stub file was generated by pyright.
"""

from abc import ABCMeta, abstractmethod
from collections.abc import MutableMapping, MutableSequence, MutableSet
from typing import Any, Iterable, Iterator, Mapping, NoReturn, Optional, Sequence, Type, TypeVar, final, overload
from enum import Enum
from coreblocks.utils import ValueLike, ShapeLike, StatementLike

__all__ = ["Shape", "signed", "unsigned", "Value", "Const", "C", "AnyConst", "AnySeq", "Operator", "Mux", "Part", "Slice", "Cat", "Repl", "Array", "ArrayProxy", "Signal", "ClockSignal", "ResetSignal", "UserValue", "ValueCastable", "Sample", "Past", "Stable", "Rose", "Fell", "Initial", "Statement", "Switch", "Property", "Assign", "Assert", "Assume", "Cover", "ValueKey", "ValueDict", "ValueSet", "SignalKey", "SignalDict", "SignalSet", "ValueLike", "ShapeLike", "StatementLike", "SwitchKey"]


T = TypeVar("T")
Flattenable = T | Iterable[Flattenable[T]]
SwitchKey = str | int | Enum


class DUID:
    """Deterministic Unique IDentifier."""
    __next_uid = ...
    def __init__(self) -> None:
        ...
    


class Shape:
    """Bit width and signedness of a va"""
    width: int
    signed: bool

    def __init__(self, width: int =..., signed: bool =...) -> None:
        ...
    
    def __iter__(self) -> Iterator[int | bool]:
        ...
    
    @staticmethod
    def cast(obj, *, src_loc_at=...):
        ...
    
    def __repr__(self) -> str:
        ...
    
    def __eq__(self, other) -> bool:
        ...
    


def unsigned(width) -> Shape:
    """Shorthand for ``Shape(width, sig"""
    ...

def signed(width) -> Shape:
    """Shorthand for ``Shape(width, sig"""
    ...

class Value(metaclass=ABCMeta):
    @staticmethod
    def cast(obj) -> Value:
        """Converts ``obj`` to an Amaranth """
        ...
    
    def __init__(self, *, src_loc_at=...) -> None:
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
    
    def __len__(self) -> int:
        ...
    
    def __getitem__(self, key: int | slice) -> Value:
        ...
    
    def as_unsigned(self) -> Value:
        """Conversion to unsigned.

       """
        ...
    
    def as_signed(self) -> Value:
        """Conversion to signed.

        R"""
        ...
    
    def bool(self) -> Value:
        """Conversion to boolean.

        """
        ...
    
    def any(self) -> Value:
        """Check if any bits are ``1``.

  """
        ...
    
    def all(self) -> Value:
        """Check if all bits are ``1``.

  """
        ...
    
    def xor(self) -> Value:
        """Compute pairwise exclusive-or of"""
        ...
    
    def implies(premise, conclusion: ValueLike) -> Value:
        """Implication.

        Returns
  """
        ...
    
    def bit_select(self, offset: ValueLike, width: int) -> Value:
        """Part-select with bit granularity"""
        ...
    
    def word_select(self, offset: ValueLike, width: int) -> Value:
        """Part-select with word granularit"""
        ...
    
    def matches(self, *patterns) -> Value:
        """Pattern matching.

        Match"""
        ...
    
    def shift_left(self, amount: int) -> Value:
        """Shift left by constant amount.

"""
        ...
    
    def shift_right(self, amount: int) -> Value:
        """Shift right by constant amount.
"""
        ...
    
    def rotate_left(self, amount: int) -> Value:
        """Rotate left by constant amount.
"""
        ...
    
    def rotate_right(self, amount: int) -> Value:
        """Rotate right by constant amount."""
        ...
    
    def eq(self, value: ValueLike) -> Assign:
        """Assignment.

        Parameters
"""
        ...
    
    @abstractmethod
    def shape(self) -> Shape:
        """Bit width and signedness of a va"""
        ...
    
    __hash__ = ...


@final
class Const(Value):
    """A constant, literal integer valu"""
    src_loc = ...
    @staticmethod
    def normalize(value, shape):
        ...
    
    def __init__(self, value: int, shape: Optional[ShapeLike] =..., *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


C = Const
class AnyValue(Value, DUID):
    def __init__(self, shape: ShapeLike, *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    


@final
class AnyConst(AnyValue):
    def __repr__(self) -> str:
        ...
    


@final
class AnySeq(AnyValue):
    def __repr__(self) -> str:
        ...
    


@final
class Operator(Value):
    def __init__(self, operator: str, operands: Iterable[ValueLike], *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


def Mux(sel: ValueLike, val1: ValueLike, val0: ValueLike) -> Value:
    """Choose between two values.

    """
    ...

@final
class Slice(Value):
    def __init__(self, value: ValueLike, start: int, stop: int, *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


@final
class Part(Value):
    def __init__(self, value: Value, offset: ValueLike, width: int, stride: int = ..., *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


@final
class Cat(Value):
    """Concatenate values.

    Form a """
    def __init__(self, *args: Flattenable[ValueLike], src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


@final
class Repl(Value):
    """Replicate a value

    An input """
    def __init__(self, value: ValueLike, count: int, *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Signal(Value, DUID):
    """A varying integer value.

    Pa"""
    def __init__(self, shape: Optional[ShapeLike] = ..., *, name: Optional[str] = ..., reset: int | Enum = ..., reset_less: bool = ..., attrs: dict = ..., decoder: type[Enum] | Callable[[int], str] = ..., src_loc_at=...) -> None:
        ...
    
    @staticmethod
    def like(other: ValueLike, *, name: Optional[str] = ..., name_suffix: Optional[str] =..., src_loc_at=..., **kwargs) -> Signal:
        """Create Signal based on another.
"""
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    
    decoder: Any


@final
class ClockSignal(Value):
    """Clock signal for a clock domain."""
    def __init__(self, domain: str = ..., *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


@final
class ResetSignal(Value):
    """Reset signal for a clock domain."""
    def __init__(self, domain: str = ..., allow_reset_less: bool = ..., *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Array(MutableSequence[T]):
    """Addressable multiplexer.

    An"""

    def __init__(self, iterable: Iterable[T] = ()) -> None:
        ...
    
    @overload
    def __getitem__(self, index: int) -> T:
        ...
    
    @overload
    def __getitem__(self, index: Value) -> ArrayProxy:
        ...

    def __getitem__(self, index: int | Value) -> T | ArrayProxy:
        ...
    
    def __len__(self) -> int:
        ...
    
    def __setitem__(self, index: int, value: T) -> None:
        ...
    
    def __delitem__(self, index: int) -> None:
        ...

    def insert(self, index: int, value: T) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


@final
class ArrayProxy(Value):
    elems: Sequence[ValueLike]
    index: Value

    def __init__(self, elems: Sequence[ValueLike], index: ValueLike, *, src_loc_at=...) -> None:
        ...
    
    def __getattr__(self, attr: str) -> ArrayProxy:
        ...
    
    def __getitem__(self, index: Value | int | str) -> ArrayProxy:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


class UserValue(Value):
    """Value with custom lowering.

   """
    @deprecated("instead of `UserValue`, use `Val", stacklevel=3)
    def __init__(self, *, src_loc_at=...) -> None:
        ...
    
    @abstractmethod
    def lower(self): # -> None:
        """Conversion to a concrete represe"""
        ...
    
    def shape(self) -> Shape:
        ...
    


class ValueCastable:
    """Base class for classes which can"""
    def __new__(cls, *args, **kwargs): # -> Self@ValueCastable:
        ...
    
    @staticmethod
    def lowermethod(func): # -> (self: Unknown, *args: Unknown, **kwargs: Unknown) -> Unknown:
        """Decorator to memoize lowering me"""
        ...
    


@final
class Sample(Value):
    """Value from the past.

    A ``Sa"""
    def __init__(self, expr: ValueLike, clocks: int, domain: Optional[str], *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


def Past(expr: ValueLike, clocks: int = ..., domain: Optional[str] = ...) -> Sample:
    ...

def Stable(expr: ValueLike, clocks: int = ..., domain: Optional[str] = ...) -> Value:
    ...

def Rose(expr: ValueLike, clocks: int = ..., domain: Optional[str] = ...) -> Value:
    ...

def Fell(expr: ValueLike, clocks: int = ..., domain: Optional[str] = ...) -> Value:
    ...

@final
class Initial(Value):
    """Start indicator, for model check"""
    def __init__(self, *, src_loc_at=...) -> None:
        ...
    
    def shape(self) -> Shape:
        ...
    
    def __repr__(self) -> str:
        ...
    


class _StatementList(list[Statement]):
    def __repr__(self) -> str:
        ...
    


class Statement:
    def __init__(self, *, src_loc_at=...) -> None:
        ...
    
    @staticmethod
    def cast(obj: StatementLike) -> _StatementList:
        ...
    


@final
class Assign(Statement):
    lhs: Value
    rhs: Value

    def __init__(self, lhs: ValueLike, rhs: ValueLike, *, src_loc_at=...) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


class Property(Statement):
    def __init__(self, test, *, _check=..., _en=..., src_loc_at=...) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


@final
class Assert(Property):
    _kind = ...


@final
class Assume(Property):
    _kind = ...


@final
class Cover(Property):
    _kind = ...


class Switch(Statement):
    def __init__(self, test: ValueLike, cases: Mapping[SwitchKey, StatementLike], *, src_loc=..., src_loc_at=..., case_src_locs=...) -> None:
        ...
    
    def __repr__(self) -> str:
        ...
    


class _MappedKeyCollection(metaclass=ABCMeta):
    ...


class _MappedKeyDict(MutableMapping, _MappedKeyCollection):
    def __init__(self, pairs=...) -> None:
        ...
    
    def __getitem__(self, key):
        ...
    
    def __setitem__(self, key, value): # -> None:
        ...
    
    def __delitem__(self, key): # -> None:
        ...
    
    def __iter__(self): # -> Generator[None, None, None]:
        ...
    
    def __eq__(self, other) -> bool:
        ...
    
    def __len__(self): # -> int:
        ...
    
    def __repr__(self): # -> str:
        ...
    


class _MappedKeySet(MutableSet, _MappedKeyCollection):
    def __init__(self, elements=...) -> None:
        ...
    
    def add(self, value): # -> None:
        ...
    
    def update(self, values): # -> None:
        ...
    
    def discard(self, value): # -> None:
        ...
    
    def __contains__(self, value): # -> bool:
        ...
    
    def __iter__(self): # -> Generator[None, None, None]:
        ...
    
    def __len__(self): # -> int:
        ...
    
    def __repr__(self): # -> str:
        ...
    


class ValueKey:
    def __init__(self, value: ValueLike) -> None:
        ...
    
    def __hash__(self) -> int:
        ...
    
    def __eq__(self, other) -> bool:
        ...
    
    def __lt__(self, other: ValueKey) -> bool:
        ...
    
    def __repr__(self) -> str:
        ...
    


class ValueDict(_MappedKeyDict):
    _map_key = ...
    _unmap_key = ...


class ValueSet(_MappedKeySet):
    _map_key = ...
    _unmap_key = ...


class SignalKey:
    def __init__(self, signal: Signal | ClockSignal | ResetSignal) -> None:
        ...
    
    def __hash__(self) -> int:
        ...
    
    def __eq__(self, other) -> bool:
        ...
    
    def __lt__(self, other: SignalKey) -> bool:
        ...
    
    def __repr__(self) -> str:
        ...
    


class SignalDict(_MappedKeyDict):
    _map_key = ...
    _unmap_key = ...


class SignalSet(_MappedKeySet):
    _map_key = ...
    _unmap_key = ...


