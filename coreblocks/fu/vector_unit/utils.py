from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import MemoryBank, Forwarder
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import RegisterLayouts

__all__ = ["EEW", "eew_to_bits"]

class EEW(IntEnum):
    w8 = auto()
    w16 = auto()
    w32 = auto()
    w64 = auto()

def eew_to_bits(eew : EEW) -> int:
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
