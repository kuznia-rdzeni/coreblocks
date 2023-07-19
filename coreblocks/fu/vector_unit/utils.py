from amaranth import *

__all__ = ["expand_mask"]


def expand_mask(v_params, mask: Value) -> Value:
    """ Converts the mask in byte format to mask in bit format.

    This function takes a mask where each bit represents whetever a byte is
    valid (1) or not (0). This mask is converted to bit format, where
    each bit of the mask represents the validity of one bit of data.

    Parameters
    ----------
    v_params : VectorParameters
        Configuration of the vector core.
    mask : Value
        The mask which should be expanded.
    """
    return Cat(Mux(mask[i], 0xFF, 0x00) for i in range(v_params.bytes_in_elen))
