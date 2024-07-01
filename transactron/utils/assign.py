from enum import Enum
from typing import Optional, TypeAlias, cast, TYPE_CHECKING
from collections.abc import Sequence, Iterable, Mapping
from amaranth import *
from amaranth.hdl import ShapeLike, ValueCastable
from amaranth.hdl._ast import ArrayProxy, Slice
from amaranth.lib import data
from ._typing import ValueLike

if TYPE_CHECKING:
    from amaranth.hdl._ast import Assign

__all__ = [
    "AssignType",
    "AssignArg",
    "assign",
]


class AssignType(Enum):
    COMMON = 1
    LHS = 2
    RHS = 3
    ALL = 4


AssignFields: TypeAlias = AssignType | Iterable[str | int] | Mapping[str | int, "AssignFields"]
AssignArg: TypeAlias = ValueLike | Mapping[str, "AssignArg"] | Mapping[int, "AssignArg"] | Sequence["AssignArg"]


def arrayproxy_fields(proxy: ArrayProxy) -> Optional[set[str | int]]:
    def flatten_elems(proxy: ArrayProxy):
        for elem in proxy.elems:
            if isinstance(elem, ArrayProxy):
                yield from flatten_elems(elem)
            else:
                yield elem

    elems = list(flatten_elems(proxy))
    if elems and all(isinstance(el, data.View) for el in elems):
        return set.intersection(*[set(cast(data.View, el).shape().members.keys()) for el in elems])


def assign_arg_fields(val: AssignArg) -> Optional[set[str | int]]:
    if isinstance(val, ArrayProxy):
        return arrayproxy_fields(val)
    elif isinstance(val, data.View):
        layout = val.shape()
        if isinstance(layout, data.StructLayout):
            return set(k for k in layout.members)
        if isinstance(layout, data.ArrayLayout):
            return set(range(layout.length))
    elif isinstance(val, dict):
        return set(val.keys())
    elif isinstance(val, list):
        return set(range(len(val)))


def valuelike_shape(val: ValueLike) -> ShapeLike:
    if isinstance(val, Value) or isinstance(val, ValueCastable):
        return val.shape()
    else:
        return Value.cast(val).shape()


def is_union(val: AssignArg):
    return isinstance(val, data.View) and isinstance(val.shape(), data.UnionLayout)


def assign(
    lhs: AssignArg, rhs: AssignArg, *, fields: AssignFields = AssignType.RHS, lhs_strict=False, rhs_strict=False
) -> Iterable["Assign"]:
    """Safe structured assignment.

    This function recursively generates assignment statements for
    field-containing structures. This includes:
    Amaranth `View`\\s using `StructLayout`, Python `dict`\\s. In case of
    mismatching fields or bit widths, error is raised.

    When both `lhs` and `rhs` are field-containing, `assign` generates
    assignment statements according to the value of the `field` parameter.
    If either of `lhs` or `rhs` is not field-containing, `assign` checks for
    the same bit width and generates a single assignment statement.

    The bit width check is performed if:

    - Any of `lhs` or `rhs` is a `View`.
    - Both `lhs` and `rhs` have an explicitly defined shape (e.g. are a
      `Signal`, a field of a `View`).

    Parameters
    ----------
    lhs : View or Value-castable or dict
        View, signal or dict being assigned.
    rhs : View or Value-castable or dict
        View, signal or dict containing assigned values.
    fields : AssignType or Iterable or Mapping, optional
        Determines which fields will be assigned. Possible values:

        AssignType.COMMON
            Only fields common to `lhs` and `rhs` are assigned.
        AssignType.LHS
            All fields in `lhs` are assigned. If one of them is not present
            in `rhs`, an exception is raised.
        AssignType.RHS
            All fields in `rhs` are assigned. If one of them is not present
            in `lhs`, an exception is raised.
        AssignType.ALL
            Assume that both structures have the same layouts. All fields present
            in `lhs` or `rhs` are assigned.
        Mapping
            Keys are field names, values follow the format for `fields`.
        Iterable
            Items are field names. For subfields, AssignType.ALL is assumed.

    Returns
    -------
    Iterable[Assign]
        Generated assignment statements.

    Raises
    ------
    ValueError
        If the assignment can't be safely performed.
    """
    lhs_fields = assign_arg_fields(lhs)
    rhs_fields = assign_arg_fields(rhs)

    def rec_call(name: str | int):
        subfields = fields
        if isinstance(fields, Mapping):
            subfields = fields[name]
        elif isinstance(fields, Iterable):
            subfields = AssignType.ALL

        return assign(
            lhs[name],  # type: ignore
            rhs[name],  # type: ignore
            fields=subfields,
            lhs_strict=isinstance(lhs, ValueLike),
            rhs_strict=isinstance(rhs, ValueLike),
        )

    if lhs_fields is not None and rhs_fields is not None:
        # asserts for type checking
        assert (
            isinstance(lhs, ArrayProxy)
            or isinstance(lhs, Mapping)
            or isinstance(lhs, Sequence)
            or isinstance(lhs, data.View)
        )
        assert (
            isinstance(rhs, ArrayProxy)
            or isinstance(rhs, Mapping)
            or isinstance(rhs, Sequence)
            or isinstance(rhs, data.View)
        )

        if fields is AssignType.COMMON:
            names = lhs_fields & rhs_fields
        elif fields is AssignType.LHS:
            names = lhs_fields
        elif fields is AssignType.RHS:
            names = rhs_fields
        elif fields is AssignType.ALL:
            names = lhs_fields | rhs_fields
        else:
            names = set(fields)

        if not names and (lhs_fields or rhs_fields):
            raise ValueError("There are no common fields in assigment lhs: {} rhs: {}".format(lhs_fields, rhs_fields))

        for name in names:
            if name not in lhs_fields:
                raise KeyError("Field {} not present in lhs".format(name))
            if name not in rhs_fields:
                raise KeyError("Field {} not present in rhs".format(name))

            yield from rec_call(name)
    elif is_union(lhs) and isinstance(rhs, Mapping) or isinstance(lhs, Mapping) and is_union(rhs):
        mapping, union = (lhs, rhs) if isinstance(lhs, Mapping) else (rhs, lhs)

        # asserts for type checking
        assert isinstance(mapping, Mapping)
        assert isinstance(union, data.View)

        if len(mapping) != 1:
            raise ValueError(f"Non-singleton mapping on union assignment lhs: {lhs} rhs: {rhs}")
        name = next(iter(mapping))

        if name not in union.shape().members:
            raise ValueError(f"Field {name} not present in union {union}")

        yield from rec_call(name)
    else:
        if not isinstance(fields, AssignType):
            raise ValueError("Fields on assigning non-structures lhs: {} rhs: {}".format(lhs, rhs))
        if not isinstance(lhs, ValueLike) or not isinstance(rhs, ValueLike):
            raise TypeError("Unsupported assignment lhs: {} rhs: {}".format(lhs, rhs))

        # If a single-value structure, assign its only field
        while lhs_fields is not None and len(lhs_fields) == 1:
            lhs = lhs[next(iter(lhs_fields))]  # type: ignore
            lhs_fields = assign_arg_fields(lhs)
        while rhs_fields is not None and len(rhs_fields) == 1:
            rhs = rhs[next(iter(rhs_fields))]  # type: ignore
            rhs_fields = assign_arg_fields(rhs)

        def has_explicit_shape(val: ValueLike):
            return isinstance(val, (Signal, ArrayProxy, Slice, ValueCastable))

        if (
            isinstance(lhs, ValueCastable)
            or isinstance(rhs, ValueCastable)
            or (lhs_strict or has_explicit_shape(lhs))
            and (rhs_strict or has_explicit_shape(rhs))
        ):
            if valuelike_shape(lhs) != valuelike_shape(rhs):
                raise ValueError(
                    "Shapes not matching: lhs: {} {} rhs: {} {}".format(
                        valuelike_shape(lhs), lhs, valuelike_shape(rhs), rhs
                    )
                )

        lhs_val = Value.cast(lhs)
        rhs_val = Value.cast(rhs)

        yield lhs_val.eq(rhs_val)
