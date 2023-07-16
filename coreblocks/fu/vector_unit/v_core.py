from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_frontend import *
from coreblocks.fu.vector_unit.v_backend import *
from coreblocks.fu.vector_unit.v_announcer import *
from coreblocks.structs_common.superscalar_freerf import *
from coreblocks.structs_common.rat import *
from utils.fifo import *

__all__ = ["VectorCore"]

# TODO retirement - listining on precommit

class VectorCore(Elaboratable):
    def __init__(self, gen_params : GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.vxrs_layouts = VectorXRSLayout(
            self.gen_params, rs_entries_bits=log2_int(self.v_params.vxrs_entries, False)
        )
        self.x_retirement_layouts = gen_params.get(RetirementLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.v_frontend_layouts = VectorFrontendLayouts(self.gen_params)

        self.insert = Method(i=self.vxrs_layouts.insert_in)
        self.select = Method(o=self.vxrs_layouts.select_out)
        self.update = Method(i=self.vxrs_layouts.update_in)
        self.precommit = Method(i = self.x_retirement_layouts.precommit)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        announcer = VectorAnnouncer(self.gen_params, 3)
        backend = VectorBackend(self.gen_params, announcer.announce_list[0])
        v_freerf = SuperscalarFreeRF(self.v_params.vrp_count, 1)
        v_frat = FRAT(gen_params = self.gen_params, superscalarity = 2)
        v_rrat = RRAT(gen_params = self.gen_params)
        fifo_to_vvrs = BasicFifo(self.v_frontend_layouts.instr_to_vvrs, 2)
        fifo_to_mem = BasicFifo(self.v_frontend_layouts.instr_to_mem, 2)
        frontend = VectorFrontend(self.gen_params, rob_block_interrupts, announcer.announce_list[1], announcer.announce_list[2], backend.report_mult, v_freerf.allocate, v_frat.get_rename_list[0], v_frat.get_rename_list[1],
                                  v_frat.set_rename_list[0], fifo_to_mem.write, fifo_to_vvrs.write, backend.initialise_regs)


        # TODO add to submodules

        return m
