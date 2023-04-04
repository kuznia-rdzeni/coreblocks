from amaranth import *


def rotate_left(sig: Value, shift: int = 1) -> Value:
    """Performs a circular left shift on the input signal by the specified (constant) shift amount."""
    return Cat(sig[-shift:], sig[:-shift])


def rotate_right(sig: Value, shift: int = 1) -> Value:
    """Performs a circular right shift on the input signal by the specified (constant) shift amount."""
    return Cat(sig[shift:], sig[:shift])
