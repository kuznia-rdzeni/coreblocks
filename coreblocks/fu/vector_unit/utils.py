from amaranth import *
from coreblocks.params import *
from coreblocks.utils import *
from coreblocks.transactions import *

__all__ = ["expand_mask", "load_store_width_to_eew", "elem_mask_to_byte_mask"]


def expand_mask(v_params, mask: Value) -> Value:
    """Converts the mask in byte format to mask in bit format.

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

def elem_mask_to_byte_mask(m: TModule, v_params: VectorParameters, elem_mask: Value, eew: Value):
    """Generate a circuit to convert the mask from the elem format to the byte format.

    The elem format always has valid first `k` bits where `k = ELEN/EEW` and each
    bit describes whether an element is valid or not. The byte format has always `ELEN//8`
    bits and each bit represents wheter a byte is valid or not.

    Parameters
    ----------
    m : TModule
        Module to connect the circuit to.
    v_params : VectorParameters
        Vector unit configuration.
    elem_mask : Value
        Mask in elem format to be converted.
    eew : Value(EEW)
        The EEW for which the `elem_mask` was generated.

    Returns
    -------
    Mask in byte format.
    """
    result = Signal(v_params.bytes_in_elen)
    with m.Switch(eew):
        for eew_iter in EEW:
            with m.Case(eew_iter):
                m.d.av_comb += result.eq(
                    Cat([Repl(bit, 2 ** int(eew_iter)) for bit in elem_mask[: v_params.elen // eew_to_bits(eew_iter)]])
                )
    return result



def load_store_width_to_eew(m : ModuleLike, width : Value) -> Signal:
    """Generate a converter from vector load/store width to EEW.

    This function decodes `width` (which is simply a funct3) from vector
    load/store instruction encodings and converts it to the corresponding data EEW.

    Parameters
    ----------
    m : TModule
        Module to connect the circuit to.
    width : Value
        Vector load/store width to decode.

    Returns
    -------
    The EEW of data on which load/store is operating.
    """
    eew = Signal(EEW)
    with m.Switch(width):
        # constants taken from RISC-V V extension specification
        with m.Case(0):
            m.d.comb += eew.eq(EEW.w8)
        with m.Case(5):
            m.d.comb += eew.eq(EEW.w16)
        with m.Case(6):
            m.d.comb += eew.eq(EEW.w32)
        with m.Case(7):
            m.d.comb += eew.eq(EEW.w64)
    return eew
