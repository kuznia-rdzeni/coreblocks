from typing import Literal, Optional, TypeAlias, cast, overload
from amaranth import *
from amaranth.utils import bits_for, log2_int
from ._typing import ValueLike, LayoutList, SignalBundle, HasElaborate, ModuleLike

__all__ = [
    "popcount",
    "count_leading_zeros",
    "count_trailing_zeros",
]



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
