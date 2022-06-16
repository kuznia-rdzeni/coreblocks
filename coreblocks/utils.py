from enum import Enum
from typing import AbstractSet, Iterable, Mapping
from amaranth import *
from amaranth.hdl.ast import Assign
from coreblocks._typing import ValueLike


__all__ = ["AssignType", "assign"]


class AssignType(Enum):
    COMMON = 1
    RHS = 2
    ALL = 3


AssignFields = AssignType | AbstractSet[str] | Mapping[str, "AssignFields"]


def assign(lhs: Signal | Record, rhs: ValueLike, *, fields: AssignFields = AssignType.RHS) -> Iterable[Assign]:
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

            if isinstance(fields, Iterable) and name not in fields:
                continue

            subFields = fields
            if isinstance(fields, Mapping):
                subFields = fields[name]
            elif isinstance(fields, AbstractSet):
                subFields = AssignType.ALL

            yield from assign(lhs.fields[name], rhs.fields[name], fields=subFields)
    else:
        if not isinstance(fields, AssignType):
            raise ValueError("Fields on assigning non-records")
        rhs = Value.cast(rhs)
        if lhs.shape() != rhs.shape():
            raise ValueError("Shapes not matching: {} and {}".format(lhs.shape(), rhs.shape()))
        yield lhs.eq(rhs)
