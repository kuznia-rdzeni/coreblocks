from coreblocks.transactions import TModule
from enum import IntEnum, auto
from amaranth.utils import *
from amaranth import *
from coreblocks.params import VectorParameters, GenParams
from coreblocks.utils._typing import ValueLike

__all__ = ["SEW", "EEW", "EMUL", "LMUL", "eew_to_bits", "bits_to_eew", "eew_div_2", "get_vlmax"]


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
    mf2 = 7 # multiply fractional 2 --> LMUL=1/2
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

def lmul_to_float(lmul : LMUL) -> float:
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

def get_vlmax(m : TModule, sew : Value, lmul : Value, gen_params : GenParams, v_params : VectorParameters) -> Signal:
    sig = Signal(gen_params.isa.xlen)
    with m.Switch((sew << len(sew)) | lmul):
        for s in SEW:
            for lm in LMUL:
                with m.Case((s << log2_int(len(SEW))) | lm):
                    m.d.comb += sig.eq(int(v_params.vlen//eew_to_bits(s)/lmul_to_float(lm)))
    return sig
