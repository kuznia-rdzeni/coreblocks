from enum import Enum
from typing import Iterable, Mapping
from amaranth import *
from amaranth.hdl.ast import Assign
from coreblocks._typing import ValueLike


__all__ = ["AssignType", "assign"]


class AssignType(Enum):
    COMMON = 1
    RHS = 2
    ALL = 3


AssignFields = AssignType | Iterable[str] | Mapping[str, "AssignFields"]


def assign(lhs: Signal | Record, rhs: ValueLike, *, fields: AssignFields = AssignType.RHS) -> Iterable[Assign]:
    """Safe record assignment.

    This function generates assignment statements for records and reports
    errors in case of mismatch. If either of ``lhs`` or ``rhs`` is not
    a Record, checks for the same bit width and generates a single
    assignment statement.

    Parameters
    ----------
    lhs : Record or Signal
        Record or signal being assigned.
    rhs : Record or Value-castable
        Record or signal containing assigned values.
    fields : AssignType or Iterable or Mapping, optional
        Determines which fields will be assigned. Possible values:

        AssignType.COMMON
            Only fields common to ``lhs`` and ``rhs`` are assigned.
        AssignType.RHS
            All fields in ``rhs`` are assigned. If one of them is not present
            in ``lhs``, an exception is raised.
        AssignType.ALL
            Assume that both records have the same layouts. All fields present
            in ``lhs`` or ``rhs`` are assigned.
        Mapping
            Keys are field names, values follow the format for ``fields``.
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
    if isinstance(lhs, Record) and isinstance(rhs, Record):
        if fields is AssignType.COMMON:
            names = set(lhs.fields) & set(rhs.fields)
        elif fields is AssignType.RHS:
            names = set(rhs.fields)
        elif fields is AssignType.ALL:
            names = set(lhs.fields) | set(rhs.fields)
        else:
            names = iter(fields)

        for name in names:
            if name not in lhs.fields:
                raise ValueError("Field {} not present in lhs".format(name))
            if name not in rhs.fields:
                raise ValueError("Field {} not present in rhs".format(name))

            subFields = fields
            if isinstance(fields, Mapping):
                subFields = fields[name]
            elif isinstance(fields, Iterable):
                subFields = AssignType.ALL

            yield from assign(lhs.fields[name], rhs.fields[name], fields=subFields)
    else:
        if not isinstance(fields, AssignType):
            raise ValueError("Fields on assigning non-records")
        rhs = Value.cast(rhs)
        if lhs.shape() != rhs.shape():
            raise ValueError("Shapes not matching: {} and {}".format(lhs.shape(), rhs.shape()))
        yield lhs.eq(rhs)
