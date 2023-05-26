"""
This type stub file was generated by pyright.
"""

from .. import *
from coreblocks.utils import HasElaborate

__all__ = ["Encoder", "Decoder", "PriorityEncoder", "PriorityDecoder", "GrayEncoder", "GrayDecoder"]
class Encoder(Elaboratable):
    """Encode one-hot to binary.

    If one bit in ``i`` is asserted, ``n`` is low and ``o`` indicates the asserted bit.
    Otherwise, ``n`` is high and ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the input

    Attributes
    ----------
    i : Signal(width), in
        One-hot input.
    o : Signal(range(width)), out
        Encoded natural binary.
    n : Signal, out
        Invalid: either none or multiple input bits are asserted.
    """
    i: Signal
    o: Signal
    n: Signal
    width: int
    def __init__(self, width: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class PriorityEncoder(Elaboratable):
    """Priority encode requests to binary.

    If any bit in ``i`` is asserted, ``n`` is low and ``o`` indicates the least significant
    asserted bit.
    Otherwise, ``n`` is high and ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the input.

    Attributes
    ----------
    i : Signal(width), in
        Input requests.
    o : Signal(range(width)), out
        Encoded natural binary.
    n : Signal, out
        Invalid: no input bits are asserted.
    """
    i: Signal
    o: Signal
    n: Signal
    def __init__(self, width: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class Decoder(Elaboratable):
    """Decode binary to one-hot.

    If ``n`` is low, only the ``i``-th bit in ``o`` is asserted.
    If ``n`` is high, ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the output.

    Attributes
    ----------
    i : Signal(range(width)), in
        Input binary.
    o : Signal(width), out
        Decoded one-hot.
    n : Signal, in
        Invalid, no output bits are to be asserted.
    """
    i: Signal
    o: Signal
    n: Signal
    width: int
    def __init__(self, width: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class PriorityDecoder(Decoder):
    """Decode binary to priority request.

    Identical to :class:`Decoder`.
    """
    ...


class GrayEncoder(Elaboratable):
    """Encode binary to Gray code.

    Parameters
    ----------
    width : int
        Bit width.

    Attributes
    ----------
    i : Signal(width), in
        Natural binary input.
    o : Signal(width), out
        Encoded Gray code.
    """
    i: Signal
    o: Signal
    width: int
    def __init__(self, width: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


class GrayDecoder(Elaboratable):
    """Decode Gray code to binary.

    Parameters
    ----------
    width : int
        Bit width.

    Attributes
    ----------
    i : Signal(width), in
        Gray code input.
    o : Signal(width), out
        Decoded natural binary.
    """
    i: Signal
    o: Signal
    width: int
    def __init__(self, width: int) -> None:
        ...
    
    def elaborate(self, platform) -> HasElaborate:
        ...
    


