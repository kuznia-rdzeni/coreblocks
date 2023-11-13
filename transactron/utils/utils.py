from contextlib import contextmanager
from enum import Enum
from typing import Literal, Optional, TypeAlias, cast, overload
from collections.abc import Iterable, Mapping
from amaranth import *
from amaranth.hdl.ast import Assign, ArrayProxy
from amaranth.lib import data
from amaranth.utils import bits_for, log2_int
from ._typing import ValueLike, LayoutList, SignalBundle, HasElaborate, ModuleLike

__all__ = [
    "AssignType",
    "assign",
    "OneHotSwitchDynamic",
    "OneHotSwitch",
    "flatten_signals",
    "align_to_power_of_two",
    "align_down_to_power_of_two",
    "bits_from_int",
    "ModuleConnector",
    "silence_mustuse",
    "popcount",
    "count_leading_zeros",
    "count_trailing_zeros",
]


@contextmanager
def OneHotSwitch(m: ModuleLike, test: Value):
    """One-hot switch.

    This function allows one-hot matching in the style similar to the standard
    Amaranth `Switch`. This allows to get the performance benefit of using
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
            with m.Case(n):
                yield

    with m.Switch(test):
        yield case


@overload
def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: Literal[True]) -> Iterable[Optional[int]]:
    ...


@overload
def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: Literal[False] = False) -> Iterable[int]:
    ...


def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: bool = False) -> Iterable[Optional[int]]:
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


def popcount(s: Value):
    sum_layers = [s[i] for i in range(len(s))]

    while len(sum_layers) > 1:
        if len(sum_layers) % 2:
            sum_layers.append(C(0))
        sum_layers = [a + b for a, b in zip(sum_layers[::2], sum_layers[1::2])]

    return sum_layers[0][0 : bits_for(len(s))]


def count_leading_zeros(s: Value) -> Value:
    def iter(s: Value, step: int) -> Value:
        # if no bits left - return empty value
        if step == 0:
            return C(0)

        # boudaries of upper and lower halfs of the value
        partition = 2 ** (step - 1)
        current_bit = 1 << (step - 1)

        # recursive call
        upper_value = iter(s[partition:], step - 1)
        lower_value = iter(s[:partition], step - 1)

        # if there are lit bits in upperhalf - take result directly from recursive value
        # otherwise add 1 << (step - 1) to lower value and return
        result = Mux(s[partition:].any(), upper_value, lower_value | current_bit)

        return result

    try:
        xlen_log = log2_int(len(s))
    except ValueError:
        raise NotImplementedError("CountLeadingZeros - only sizes aligned to power of 2 are supperted")

    value = iter(s, xlen_log)

    # 0 number edge case
    # if s == 0 then iter() returns value off by 1
    # this switch negates this effect
    high_bit = 1 << xlen_log

    result = Mux(s.any(), value, high_bit)
    return result


def count_trailing_zeros(s: Value) -> Value:
    try:
        log2_int(len(s))
    except ValueError:
        raise NotImplementedError("CountTrailingZeros - only sizes aligned to power of 2 are supperted")

    return count_leading_zeros(s[::-1])


def layout_subset(layout: LayoutList, *, fields: set[str]) -> LayoutList:
    return [item for item in layout if item[0] in fields]


def flatten_signals(signals: SignalBundle) -> Iterable[Signal]:
    """
    Flattens input data, which can be either a signal, a record, a list (or a dict) of SignalBundle items.

    """
    if isinstance(signals, Mapping):
        for x in signals.values():
            yield from flatten_signals(x)
    elif isinstance(signals, Iterable):
        for x in signals:
            yield from flatten_signals(x)
    elif isinstance(signals, Record):
        for x in signals.fields.values():
            yield from flatten_signals(x)
    elif isinstance(signals, data.View):
        for x, _ in signals.shape():
            yield from flatten_signals(signals[x])
    else:
        yield signals


def align_to_power_of_two(num: int, power: int) -> int:
    """Rounds up a number to the given power of two.

    Parameters
    ----------
    num : int
        The number to align.
    power : int
        The power of two to align to.

    Returns
    -------
    int
        The aligned number.
    """
    mask = 2**power - 1
    if num & mask == 0:
        return num
    return (num & ~mask) + 2**power


def align_down_to_power_of_two(num: int, power: int) -> int:
    """Rounds down a number to the given power of two.

    Parameters
    ----------
    num : int
        The number to align.
    power : int
        The power of two to align to.

    Returns
    -------
    int
        The aligned number.
    """
    mask = 2**power - 1

    return num & ~mask


def bits_from_int(num: int, lower: int, length: int):
    """Returns [`lower`:`lower`+`length`) bits from integer `num`."""
    return (num >> lower) & ((1 << (length)) - 1)


class ModuleConnector(Elaboratable):
    """
    An Elaboratable to create a new module, which will have all arguments
    added as its submodules.
    """

    def __init__(self, *args: HasElaborate, **kwargs: HasElaborate):
        """
        Parameters
        ----------
        *args
            Modules which should be added as anonymous submodules.
        **kwargs
            Modules which will be added as named submodules.
        """
        self.args = args
        self.kwargs = kwargs

    def elaborate(self, platform):
        m = Module()

        for elem in self.args:
            m.submodules += elem

        for name, elem in self.kwargs.items():
            m.submodules[name] = elem

        return m


@contextmanager
def silence_mustuse(elaboratable: Elaboratable):
    try:
        yield
    except Exception:
        elaboratable._MustUse__silence = True  # type: ignore
        raise
