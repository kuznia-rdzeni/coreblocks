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
from coreblocks.fu.vector_unit.v_insert_to_vvrs import *
from coreblocks.structs_common.scoreboard import *


class VectorBackend(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.layouts = VectorBackendLayouts(self.gen_params)

        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.v_params.vvrs_entries_bits)

        self.put_instr = Method(i=self.layouts.vvrs_in)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.ready_scoreboard = ready_scoreboard = Scoreboard(self.v_params.vrp_count, superscalarity = 4)
        m.submodules.vvrs = vvrs = VVRS(self.gen_params, self.v_params.vvrs_entries_bits)
        m.submodules.insert_to_vvrs = insert_to_vvrs = VectorInsertToVVRS(self.gen_params, vvrs.select, vvrs.insert, ready_scoreboard.get_dirty_list)
        
        self.put_instr.proxy(m, insert_to_vvrs.issue)

        return m
