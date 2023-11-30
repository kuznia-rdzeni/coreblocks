"""
This type stub file was generated by pyright.
"""

import enum as py_enum
from typing import Generic, Optional, TypeVar, overload
from typing_extensions import Self
from amaranth import *
from ..hdl.ast import Assign, ValueCastable, ShapeCastable, ValueLike

__all__ = ['EnumMeta', 'Enum', 'IntEnum', 'Flag', 'IntFlag', 'EnumView', 'FlagView', 'auto', 'unique']


_T_EnumMeta = TypeVar("_T_EnumMeta", bound=EnumMeta)
_T = TypeVar("_T")
_T_ViewClass = TypeVar("_T_ViewClass", bound=None | ValueCastable)


auto = py_enum.auto
unique = py_enum.unique


class EnumMeta(ShapeCastable, py_enum.EnumMeta, Generic[_T_ViewClass]):
    """Subclass of the standard :class:`enum.EnumMeta` that implements the :class:`ShapeCastable`
    protocol.

    This metaclass provides the :meth:`as_shape` method, making its instances
    :ref:`shape-castable <lang-shapecasting>`, and accepts a ``shape=`` keyword argument
    to specify a shape explicitly. Other than this, it acts the same as the standard
    :class:`enum.EnumMeta` class; if the ``shape=`` argument is not specified and
    :meth:`as_shape` is never called, it places no restrictions on the enumeration class
    or the values of its members.
    """
    @classmethod
    def __prepare__(metacls, name, bases, shape: Shape=..., view_class:_T_ViewClass=..., **kwargs) -> py_enum._EnumDict:
        ...
    
    def __new__(cls, name, bases, namespace, shape: Shape=..., view_class:_T_ViewClass=..., **kwargs) -> Self:
        ...
    
    def as_shape(cls) -> Shape:
        """Cast this enumeration to a shape.

        Returns
        -------
        :class:`Shape`
            Explicitly provided shape. If not provided, returns the result of shape-casting
            this class :ref:`as a standard Python enumeration <lang-shapeenum>`.

        Raises
        ------
        TypeError
            If the enumeration has neither an explicitly provided shape nor any members.
        """
        ...
    
    @overload
    def __call__(cls: type[_T], value: int) -> _T:
        ...

    @overload
    def __call__(cls: type[_T], value: _T) -> _T:
        ...

    @overload
    def __call__(cls: EnumMeta[None], value: int | ValueLike) -> Value:
        ...

    @overload
    def __call__(cls: EnumMeta[_T_ViewClass], value: int | ValueLike) -> _T_ViewClass:
        ...

    def __call__(cls, value: int | ValueLike) -> Value | ValueCastable:
        ...
    
    def const(cls, init) -> Const:
        ...
    

class E(IntEnum):
    X = 1

x = E(5)

class Enum(py_enum.Enum, metaclass=EnumMeta[EnumView]):
    """Subclass of the standard :class:`enum.Enum` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class IntEnum(py_enum.IntEnum, metaclass=EnumMeta[None]):
    """Subclass of the standard :class:`enum.IntEnum` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class Flag(py_enum.Flag, metaclass=EnumMeta[FlagView]):
    """Subclass of the standard :class:`enum.Flag` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class IntFlag(py_enum.IntFlag, metaclass=EnumMeta[None]):
    """Subclass of the standard :class:`enum.IntFlag` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class EnumView(ValueCastable, Generic[_T_EnumMeta]):
    """The view class used for :class:`Enum`.

    Wraps a :class:`Value` and only allows type-safe operations. The only operators allowed are
    equality comparisons (``==`` and ``!=``) with another :class:`EnumView` of the same enum type.
    """

    def __init__(self, enum: _T_EnumMeta, target: ValueLike):
        ...

    def shape(self) -> _T_EnumMeta:
        ...

    @ValueCastable.lowermethod
    def as_value(self) -> Value:
        ...

    def eq(self, other: ValueLike) -> Assign:
        ...

    def __eq__(self, other: FlagView[_T_EnumMeta] | _T_EnumMeta) -> Value:
        """Compares the underlying value for equality.

        The other operand has to be either another :class:`EnumView` with the same enum type, or
        a plain value of the underlying enum.

        Returns
        -------
        :class:`Value`
            The result of the equality comparison, as a single-bit value.
        """
        ...

    def __ne__(self, other: FlagView[_T_EnumMeta] | _T_EnumMeta) -> Value:
        ...



class FlagView(EnumView[_T_EnumMeta], Generic[_T_EnumMeta]):
    """The view class used for :class:`Flag`.

    In addition to the operations allowed by :class:`EnumView`, it allows bitwise operations among
    values of the same enum type."""

    def __invert__(self) -> FlagView[_T_EnumMeta]:
        """Inverts all flags in this value and returns another :ref:`FlagView`.

        Note that this is not equivalent to applying bitwise negation to the underlying value:
        just like the Python :class:`enum.Flag` class, only bits corresponding to flags actually
        defined in the enumeration are included in the result.

        Returns
        -------
        :class:`FlagView`
        """
        ...

    def __and__(self, other: FlagView[_T_EnumMeta] | _T_EnumMeta) -> FlagView[_T_EnumMeta]:
        """Performs a bitwise AND and returns another :class:`FlagView`.

        The other operand has to be either another :class:`FlagView` of the same enum type, or
        a plain value of the underlying enum type.

        Returns
        -------
        :class:`FlagView`
        """
        ...

    def __or__(self, other: FlagView[_T_EnumMeta] | _T_EnumMeta) -> FlagView[_T_EnumMeta]:
        """Performs a bitwise OR and returns another :class:`FlagView`.

        The other operand has to be either another :class:`FlagView` of the same enum type, or
        a plain value of the underlying enum type.

        Returns
        -------
        :class:`FlagView`
        """
        ...

    def __xor__(self, other: FlagView[_T_EnumMeta] | _T_EnumMeta) -> FlagView[_T_EnumMeta]:
        """Performs a bitwise XOR and returns another :class:`FlagView`.

        The other operand has to be either another :class:`FlagView` of the same enum type, or
        a plain value of the underlying enum type.

        Returns
        -------
        :class:`FlagView`
        """
        ...

    __rand__ = __and__
    __ror__ = __or__
    __rxor__ = __xor__



