from amaranth import *
from typing import Optional, Iterable
from coreblocks.transactions import *
from coreblocks.structs_common.rs import RS
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *

class VRS(RS):
    def __init__(self, gen_params: GenParams, rs_entries: int, insert_hook : Optional[Method] = None, ready_for: Optional[Iterable[Iterable[OpType]]] = None) -> None:
        super().__init__(gen_params, rs_entries, ready_for, layout_class=VectorRSLayout, insert_hook = insert_hook)
