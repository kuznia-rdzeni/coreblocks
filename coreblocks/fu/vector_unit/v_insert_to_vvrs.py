from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.structs_common.scoreboard import *

__all__ = ["VectorInsertToVVRS"]

class VectorInsertToVVRS(Elaboratable):
    def __init__(self, gen_params : GenParams, select : Method, insert : Method, scoreboard_get_list : list[Method]):
        self.gen_params = gen_params
        self.select = select
        self.insert = insert
        self.scoreboard_get_list = scoreboard_get_list

        if len(self.scoreboard_get_list) < 4:
            raise ValueError("VectorInsertToVVRS need minimum 4 methods to read scoreboard.")

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.gen_params.v_params.vvrs_entries_bits)
        self.issue = Method(i = self.layouts.vvrs_in)

    def elaborate(self, platform):
        m = TModule()

        
        @def_method(m, self.issue)
        def _(arg):
            rs_entry_id = self.select(m)
            rs_data = Record(self.vvrs_layouts.data_layout)
            m.d.comb += assign(rs_data, arg)
            for i, rp in enumerate(["rp_s1_rdy", "rp_s2_rdy", "rp_s3_rdy", "rp_v0_rdy"]):
                m.d.comb += rs_data[rp].eq(self.scoreboard_get_list[1](m).dirty)
            insert_data = { "rs_entry_id" : rs_entry_id, "rs_data" : rs_data }
            self.insert(m, insert_data)

        return m
