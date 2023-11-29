"""
This type stub file was generated by pyright.
"""

import enum as py_enum
from typing_extensions import Self
from amaranth import *
from ..hdl.ast import ShapeCastable

__all__ = ['EnumMeta', 'Enum', 'IntEnum', 'Flag', 'IntFlag', 'auto', 'unique']


auto = py_enum.auto
unique = py_enum.unique


# TODO: update stubs for enums


class EnumMeta(ShapeCastable, py_enum.EnumMeta):
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
    def __prepare__(metacls, name, bases, shape=..., **kwargs) -> py_enum._EnumDict:
        ...
    
    def __new__(cls, name, bases, namespace, shape=..., **kwargs) -> Self:
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
    
    def __call__(cls, value) -> Value:
        ...
    
    def const(cls, init) -> Const:
        ...
    


class Enum(py_enum.Enum, metaclass=EnumMeta):
    """Subclass of the standard :class:`enum.Enum` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class IntEnum(py_enum.IntEnum, metaclass=EnumMeta):
    """Subclass of the standard :class:`enum.IntEnum` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class Flag(py_enum.Flag, metaclass=EnumMeta):
    """Subclass of the standard :class:`enum.Flag` that has :class:`EnumMeta` as
    its metaclass."""
    ...


class IntFlag(py_enum.IntFlag, metaclass=EnumMeta):
    """Subclass of the standard :class:`enum.IntFlag` that has :class:`EnumMeta` as
    its metaclass."""
    ...


