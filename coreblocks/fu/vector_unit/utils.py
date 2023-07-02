from enum import IntEnum, auto

__all__ = ["SEW", "EEW", "EMUL", "LMUL", "eew_to_bits", "bits_to_eew", "eew_div_2"]


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


