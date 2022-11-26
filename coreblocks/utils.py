from contextlib import contextmanager
from enum import Enum
from typing import Iterable, Literal, Mapping, Optional, overload
from amaranth import *
from amaranth.hdl.ast import Assign
from coreblocks._typing import ValueLike


__all__ = ["AssignType", "assign", "OneHotSwitchDynamic", "OneHotSwitch"]


@contextmanager
def OneHotSwitch(m: Module, test: Value):
    """One-hot switch.

    This function allows one-hot matching in the style similar to the standard
    Amaranth ``Switch``. This allows to get the performance benefit of using
    the one-hot representation.

    Example::

        with OneHotSwitch(m, sig) as OneHotCase:
            with OneHotCase(0b01):
                ...
            with OneHotCase(0b10):
                ...
            # optional default case
            with OneHotCase():
                ...

    Parameters
    ----------
    m : Module
        The module for which the matching is defined.
    test : Signal
        The signal being tested.
    """
    count = len(test)

    @contextmanager
    def case(n: Optional[int] = None):
        if n is None:
            with m.Case():
                yield
        else:
            # find the index of the least significant bit set
            i = (n & -n).bit_length() - 1
            if n - (1 << i) != 0:
                raise ValueError("%d not in one-hot representation" % n)
            with m.Case("-" * (count - i - 1) + "1" + "-" * i):
                yield

    with m.Switch(test):
        yield case


@overload
def OneHotSwitchDynamic(m: Module, test: Value, *, default: Literal[True]) -> Iterable[Optional[int]]:
    ...


@overload
def OneHotSwitchDynamic(m: Module, test: Value, *, default: Literal[False] = False) -> Iterable[int]:
    ...


def OneHotSwitchDynamic(m: Module, test: Value, *, default: bool = False) -> Iterable[Optional[int]]:
    """Dynamic one-hot switch.

    This function allows simple one-hot matching on signals which can have
    variable bit widths.

    Example::

        for i in OneHotSwitchDynamic(m, sig):
            # code dependent on the bit index i
            ...

    Parameters
    ----------
    m : Module
        The module for which the matching is defined.
    test : Signal
        The signal being tested.
    default : bool, optional
        Whether the matching includes a default case (signified by a None).
    """
    count = len(test)
    with OneHotSwitch(m, test) as OneHotCase:
        for i in range(count):
            with OneHotCase(1 << i):
                yield i
        if default:
            with OneHotCase():
                yield None
    return


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
            names = set(fields)

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
