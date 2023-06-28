from enum import IntEnum, auto

__all__ = ["EEW", "eew_to_bits", "bits_to_eew", "eew_div_2"]


class EEW(IntEnum):
    """Representation of possible EEW

    This enum represents EEWs as defined by the V extension, that
    we are able to support in our core.

    Possible values are represented by the small integer numbers to
    compress the representation as much as possible. So it dosn't
    take much HW resources to represent an EEW.
    """

    w8 = auto()
    w16 = auto()
    w32 = auto()
    w64 = auto()


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
