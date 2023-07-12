from amaranth import *

__all__ = ["expand_mask"]

def expand_mask(v_params, mask: Value) -> Value:
    return Cat(Mux(mask[i], 0xFF, 0x00) for i in range(v_params.bytes_in_elen))


