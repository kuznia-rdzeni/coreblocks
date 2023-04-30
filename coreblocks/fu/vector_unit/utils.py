from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.transactions.lib import MemoryBank, Forwarder
from coreblocks.params import *
from coreblocks.params.vector_params import VectorParameters
from coreblocks.fu.vector_unit.v_layouts import RegisterLayouts

__all__ = ["EEW"]

class EEW(IntEnum):
    w8 = auto()
    w16 = auto()
    w32 = auto()
    w64 = auto()


