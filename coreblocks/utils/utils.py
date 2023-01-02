from contextlib import contextmanager
from enum import Enum
from typing import Iterable, Literal, Mapping, Optional, overload
from amaranth import *
from amaranth.hdl.ast import Assign, ArrayProxy
from ._typing import ValueLike


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


def arrayproxy_fields(proxy: ArrayProxy) -> Optional[set[str]]:
    def flatten_elems(proxy: ArrayProxy):
        for elem in proxy.elems:
            if isinstance(elem, ArrayProxy):
                yield from flatten_elems(elem)
            else:
                yield elem

    elems = list(flatten_elems(proxy))
    if elems and all(isinstance(el, Record) for el in elems):
        return set.intersection(*[set(el.fields) for el in elems])


def valuelike_fields(val: ValueLike) -> Optional[set[str]]:
    if isinstance(val, ArrayProxy):
        return arrayproxy_fields(val)
    elif isinstance(val, Record):
        return set(val.fields)


def assign(
    lhs: Signal | Record | ArrayProxy, rhs: ValueLike, *, fields: AssignFields = AssignType.RHS
) -> Iterable[Assign]:
    """Safe record assignment.

    This function generates assignment statements for records and reports
    errors in case of mismatch. If either of ``lhs`` or ``rhs`` is not
    a Record, checks for the same bit width and generates a single
    assignment statement.

    Parameters
    ----------
    lhs : Record or Signal or ArrayProxy
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
    lhs_fields = valuelike_fields(lhs)
    rhs_fields = valuelike_fields(rhs)

    if lhs_fields is not None and rhs_fields is not None:
        # asserts for type checking
        assert isinstance(lhs, Record) or isinstance(lhs, ArrayProxy)
        assert isinstance(rhs, Record) or isinstance(rhs, ArrayProxy)

        if fields is AssignType.COMMON:
            names = lhs_fields & rhs_fields
        elif fields is AssignType.RHS:
            names = rhs_fields
        elif fields is AssignType.ALL:
            names = lhs_fields | rhs_fields
        else:
            names = set(fields)

        for name in names:
            if name not in lhs_fields:
                raise ValueError("Field {} not present in lhs".format(name))
            if name not in rhs_fields:
                raise ValueError("Field {} not present in rhs".format(name))

            subfields = fields
            if isinstance(fields, Mapping):
                subfields = fields[name]
            elif isinstance(fields, Iterable):
                subfields = AssignType.ALL

            yield from assign(lhs[name], rhs[name], fields=subfields)
    else:
        if not isinstance(fields, AssignType):
            raise ValueError("Fields on assigning non-records")
        rhs = Value.cast(rhs)
        if lhs.shape() != rhs.shape():
            raise ValueError("Shapes not matching: {} and {}".format(lhs.shape(), rhs.shape()))
        yield lhs.eq(rhs)
