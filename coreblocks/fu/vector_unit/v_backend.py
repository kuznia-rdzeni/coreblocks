from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.fu.vector_unit.v_insert_to_vvrs import *
from coreblocks.structs_common.scoreboard import *
from coreblocks.fu.vector_unit.v_needed_regs import *
from coreblocks.fu.vector_unit.v_len_getter import *
from coreblocks.fu.vector_unit.v_elems_downloader import *
from coreblocks.fu.vector_unit.v_elems_uploader import *
from coreblocks.fu.vector_unit.v_mask_extractor import *
from coreblocks.fu.vector_unit.v_execution_ender import *
from coreblocks.fu.vector_unit.vector_alu import *
from coreblocks.fu.vector_unit.vrf import *
from coreblocks.fu.vector_unit.v_execution_data_spliter import *

# TODO optimise by allowing to start porcessing new register while old is still being uploaded

# TODO - downloader should download v0 from address//8
# TODO - initialize regs somewhere
# TODO - handle rp_dst == RegisterType.X
# TODO - handle tail undisturbed elements

class VectorBackend(Elaboratable):
    def __init__(self, gen_params: GenParams, announce : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.announce = announce

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.v_params.vvrs_entries_bits)
        self.alu_layouts = VectorAluLayouts(self.gen_params)

        self.put_instr = Method(i=self.layouts.vvrs_in)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        # TODO pamiętać o podłączeniu rozgłaszania
        m.submodules.ready_scoreboard = ready_scoreboard = Scoreboard(self.v_params.vrp_count, superscalarity = 4)
        m.submodules.vvrs = vvrs = VVRS(self.gen_params, self.v_params.vvrs_entries_bits)
        m.submodules.insert_to_vvrs = insert_to_vvrs = VectorInsertToVVRS(self.gen_params, vvrs.select, vvrs.insert, ready_scoreboard.get_dirty_list)
        
        self.put_instr.proxy(m, insert_to_vvrs.issue)

        m.submodules.ender = ender = VectorExecutionEnder(self.gen_params, self.announce)
        needed_regs_write_to_fifos = []

            #TODO  ender
        needed_regs_product_pusher = MethodProduct(needed_regs_write_to_fifos)
        wakeup_select = WakeupSelect(gen_params = self.gen_params, get_ready = vvrs.get_ready_list[0], take_row = vvrs.take, issue = needed_regs_transformer.method, row_layout = self.layouts.vvrs_out)

            

        return m
