from typing import Iterable
from amaranth import *
from amaranth.hdl.ast import Assign
from coreblocks._typing import ValueLike


def assign(lhs: Signal | Record, rhs: ValueLike, *, fromAll: bool = True, toAll: bool = False) -> Iterable[Assign]:
    if isinstance(lhs, Record) and isinstance(rhs, Record):
        for (name, rfield) in rhs.fields.items():
            if name not in lhs.fields:
                if fromAll:
                    raise ValueError("Field {} not present in lhs".format(name))
                continue
            lfield = lhs.fields[name]
            yield from assign(lfield, rfield, fromAll=fromAll, toAll=toAll)
        if toAll:
            for name in lhs.fields.keys():
                if name not in rhs.fields:
                    raise ValueError("Field {} not present in rhs".format(name))
    else:
        rhs = Value.cast(rhs)
        if lhs.shape() != rhs.shape():
            raise ValueError("Shapes not matching: {} and {}".format(lhs.shape(), rhs.shape()))
        yield lhs.eq(rhs)
