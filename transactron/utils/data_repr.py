from collections.abc import Iterable, Mapping
from ._typing import ShapeLike, MethodLayout
from typing import Any, Sized
from statistics import fmean
from amaranth.lib.data import StructLayout


__all__ = [
    "make_hashable",
    "align_to_power_of_two",
    "align_down_to_power_of_two",
    "bits_from_int",
    "layout_subset",
    "data_layout",
    "signed_to_int",
    "int_to_signed",
    "neg",
    "average_dict_of_lists",
]


def layout_subset(layout: StructLayout, *, fields: set[str]) -> StructLayout:
    return StructLayout({item: value for item, value in layout.members.items() if item in fields})


def make_hashable(val):
    if isinstance(val, Mapping):
        return frozenset(((k, make_hashable(v)) for k, v in val.items()))
    elif isinstance(val, Iterable):
        return (make_hashable(v) for v in val)
    else:
        return val


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


def data_layout(val: ShapeLike) -> MethodLayout:
    return [("data", val)]


def neg(x: int, xlen: int) -> int:
    """
    Computes the negation of a number in the U2 system.

    Parameters
    ----------
    x: int
        Number in U2 system.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Negation of x in the U2 system.
    """
    return (-x) & (2**xlen - 1)


def int_to_signed(x: int, xlen: int) -> int:
    """
    Converts a Python integer into its U2 representation.

    Parameters
    ----------
    x: int
        Signed Python integer.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Representation of x in the U2 system.
    """
    return x & (2**xlen - 1)


def signed_to_int(x: int, xlen: int) -> int:
    """
    Changes U2 representation into Python integer

    Parameters
    ----------
    x: int
        Number in U2 system.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Representation of x as signed Python integer.
    """
    return x | -(x & (2 ** (xlen - 1)))


def average_dict_of_lists(d: Mapping[Any, Sized]) -> float:
    return fmean(map(lambda xs: len(xs), d.values()))
