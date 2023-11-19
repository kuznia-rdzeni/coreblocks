from enum import Enum
from typing import Optional, TypeAlias, cast
from collections.abc import Iterable, Mapping
from amaranth import *
from amaranth.hdl.ast import Assign, ArrayProxy
from amaranth.lib import data
from ._typing import ValueLike

__all__ = [
    "AssignType",
    "assign",
]


class AssignType(Enum):
    COMMON = 1
    RHS = 2
    ALL = 3


AssignFields: TypeAlias = AssignType | Iterable[str] | Mapping[str, "AssignFields"]
AssignArg: TypeAlias = ValueLike | Mapping[str, "AssignArg"]


def arrayproxy_fields(proxy: ArrayProxy) -> Optional[set[str]]:
    def flatten_elems(proxy: ArrayProxy):
        for elem in proxy.elems:
            if isinstance(elem, ArrayProxy):
                yield from flatten_elems(elem)
            else:
                yield elem

    elems = list(flatten_elems(proxy))
    if elems and all(isinstance(el, Record) for el in elems):
        return set.intersection(*[set(cast(Record, el).fields) for el in elems])


def assign_arg_fields(val: AssignArg) -> Optional[set[str]]:
    if isinstance(val, ArrayProxy):
        return arrayproxy_fields(val)
    elif isinstance(val, Record):
        return set(val.fields)
    elif isinstance(val, data.View):
        layout = val.shape()
        if isinstance(layout, data.StructLayout):
            return set(k for k, _ in layout)
    elif isinstance(val, dict):
        return set(val.keys())


def assign(
    lhs: AssignArg, rhs: AssignArg, *, fields: AssignFields = AssignType.RHS, lhs_strict=False, rhs_strict=False
) -> Iterable[Assign]:
    """Safe record assignment.

    This function recursively generates assignment statements for
    field-containing structures. This includes: Amaranth `Record`\\s,
    Amaranth `View`\\s using `StructLayout`, Python `dict`\\s. In case of
    mismatching fields or bit widths, error is raised.

    When both `lhs` and `rhs` are field-containing, `assign` generates
    assignment statements according to the value of the `field` parameter.
    If either of `lhs` or `rhs` is not field-containing, `assign` checks for
    the same bit width and generates a single assignment statement.

    The bit width check is performed if:

    - Any of `lhs` or `rhs` is a `Record` or `View`.
    - Both `lhs` and `rhs` have an explicitly defined shape (e.g. are a
      `Signal`, a field of a `Record` or a `View`).

    Parameters
    ----------
    lhs : Record or View or Value-castable or dict
        Record, signal or dict being assigned.
    rhs : Record or View or Value-castable or dict
        Record, signal or dict containing assigned values.
    fields : AssignType or Iterable or Mapping, optional
        Determines which fields will be assigned. Possible values:

        AssignType.COMMON
            Only fields common to `lhs` and `rhs` are assigned.
        AssignType.RHS
            All fields in `rhs` are assigned. If one of them is not present
            in `lhs`, an exception is raised.
        AssignType.ALL
            Assume that both records have the same layouts. All fields present
            in `lhs` or `rhs` are assigned.
        Mapping
            Keys are field names, values follow the format for `fields`.
        Iterable
            Items are field names. For subrecords, AssignType.ALL is assumed.

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

    if lhs_fields is not None and rhs_fields is not None:
        # asserts for type checking
        assert (
            isinstance(lhs, Record)
            or isinstance(lhs, ArrayProxy)
            or isinstance(lhs, Mapping)
            or isinstance(lhs, data.View)
        )
        assert (
            isinstance(rhs, Record)
            or isinstance(rhs, ArrayProxy)
            or isinstance(rhs, Mapping)
            or isinstance(rhs, data.View)
        )

        if fields is AssignType.COMMON:
            names = lhs_fields & rhs_fields
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

            subfields = fields
            if isinstance(fields, Mapping):
                subfields = fields[name]
            elif isinstance(fields, Iterable):
                subfields = AssignType.ALL

            yield from assign(
                lhs[name],
                rhs[name],
                fields=subfields,
                lhs_strict=not isinstance(lhs, Mapping),
                rhs_strict=not isinstance(rhs, Mapping),
            )
    else:
        if not isinstance(fields, AssignType):
            raise ValueError("Fields on assigning non-records")
        if not isinstance(lhs, ValueLike) or not isinstance(rhs, ValueLike):
            raise TypeError("Unsupported assignment lhs: {} rhs: {}".format(lhs, rhs))

        lhs_val = Value.cast(lhs)
        rhs_val = Value.cast(rhs)

        def has_explicit_shape(val: ValueLike):
            return isinstance(val, Signal) or isinstance(val, ArrayProxy)

        if (
            isinstance(lhs, Record)
            or isinstance(rhs, Record)
            or isinstance(lhs, data.View)
            or isinstance(rhs, data.View)
            or (lhs_strict or has_explicit_shape(lhs))
            and (rhs_strict or has_explicit_shape(rhs))
        ):
            if lhs_val.shape() != rhs_val.shape():
                raise ValueError(
                    "Shapes not matching: lhs: {} {} rhs: {} {}".format(lhs_val.shape(), lhs, rhs_val.shape(), rhs)
                )
        yield lhs_val.eq(rhs_val)
