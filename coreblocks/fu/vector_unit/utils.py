import math
from enum import IntEnum
from amaranth.utils import *
from amaranth import *
from coreblocks.params import VectorParameters, GenParams
from coreblocks.utils._typing import ModuleLike

__all__ = [
    "SEW",
    "EEW",
    "EMUL",
    "LMUL",
    "eew_to_bits",
    "bits_to_eew",
    "eew_div_2",
    "get_vlmax",
    "lmul_to_float",
    "lmul_to_int",
]


class SEW(IntEnum):
    """Representation of possible SEW

    This enum represents SEWs as defined by the V extension, that
    we are able to support in our core.

    Possible values are represented by the small integer numbers to
    compress the representation as much as possible. So it dosn't
    take much HW resources to represent an SEW.
    """

    w8 = 0
    w16 = 1
    w32 = 2
    w64 = 3


EEW = SEW


class LMUL(IntEnum):
    m1 = 0
    m2 = 1
    m4 = 2
    m8 = 3
    mf2 = 7  # multiply fractional 2 --> LMUL=1/2
    mf4 = 6
    mf8 = 5


EMUL = LMUL


def eew_to_bits(eew: EEW) -> int:
    """Convert EEW to number of bits

    This function takes an eew in the form of enum and converts it to an
    integer representing the width in bits of an element for the given eew.

    Parameters
    ----------
    eew : EEW
        EEW to convert to bit length.

    Returns
    -------
    width : int
        The width in bits of an element for the given eew.
    """
    if eew == EEW.w8:
        return 8
    elif eew == EEW.w16:
        return 16
    elif eew == EEW.w32:
        return 32
    elif eew == EEW.w64:
        return 64
    else:
        raise ValueError(f"Not known EEW: {eew}")


def bits_to_eew(bits: int) -> EEW:
    """Convert width in bits to EEW

    Parameters
    ----------
    bits : int
        The width of an element in bits.

    Returns
    -------
    eew : EEW
        EEW representing elements with the given width.
    """
    if bits == 8:
        return EEW.w8
    elif bits == 16:
        return EEW.w16
    elif bits == 32:
        return EEW.w32
    elif bits == 64:
        return EEW.w64
    else:
        raise ValueError(f"Not known EEW: {bits}")


def eew_div_2(eew: EEW) -> EEW:
    """Reduce EEW by 2

    This function is a shortcut to easily reduce the EEW width by a factor of 2.

    Parameters
    ----------
    eew : EEW
        EEW to be divided by 2.
    """
    return bits_to_eew(eew_to_bits(eew) // 2)


def lmul_to_float(lmul: LMUL) -> float:
    """Converts LMUL to float

    Parameters
    ----------
    lmul : LMUL
        The lmul to convert.

    Returns
    -------
    float
        The multiplier that is represented by `lmul`.
    """
    match lmul:
        case LMUL.m1:
            return 1
        case LMUL.m2:
            return 2
        case LMUL.m4:
            return 4
        case LMUL.m8:
            return 8
        case LMUL.mf2:
            return 0.5
        case LMUL.mf4:
            return 0.25
        case LMUL.mf8:
            return 0.125


def get_vlmax(m: ModuleLike, sew: Value, lmul: Value, gen_params: GenParams, v_params: VectorParameters) -> Signal:
    """Generates circuit to calculate VLMAX

    This function generates a circuit that computes in
    combinational domain, a VLMAX based on the `sew` and
    `lmul` signals, taking into account the `vlen` configured in
    `v_params`.

    Parameters
    ----------
    m : ModuleLike
        Module to connect the generated circuit to.
    sew : Value
        SEW for which VLMAX should is to be calculated.
    lmul : Value
        LMUL for which VLMAX should is to be calculated.
    gen_params : GenParams
        Configuration of the core.
    v_params : VectorParameters
        Configuration of the vector extension.

    Returns
    -------
    vlmax : Signal
        Signal containing the calculated VLMAX.
    """
    sig = Signal(gen_params.isa.xlen)
    with m.Switch((sew << len(lmul)) | lmul):
        for s in SEW:
            for lm in LMUL:
                bits = (s << log2_int(len(LMUL), False)) | lm
                with m.Case(bits):
                    val = int(v_params.vlen // eew_to_bits(s) * lmul_to_float(lm))
                    m.d.comb += sig.eq(val)
    return sig


def lmul_to_int(lmul: LMUL) -> int:
    """Convert LMUL to int by rounding up.

    Parameters
    ----------
    lmul : LMUL
        Value to convert.
    """
    return math.ceil(lmul_to_float(lmul))
