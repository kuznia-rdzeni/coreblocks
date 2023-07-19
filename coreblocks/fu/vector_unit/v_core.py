from amaranth import *
from dataclasses import dataclass
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_frontend import *
from coreblocks.fu.vector_unit.v_backend import *
from coreblocks.fu.vector_unit.v_announcer import *
from coreblocks.fu.vector_unit.v_retirement import *
from coreblocks.structs_common.superscalar_freerf import *
from coreblocks.structs_common.rat import *
from coreblocks.utils.fifo import *
from coreblocks.utils.protocols import FuncBlock

__all__ = ["VectorCore"]


class VectorCore(Elaboratable):
    def __init__(self, gen_params: GenParams):
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
        self.precommit = Method(i=self.x_retirement_layouts.precommit)
        self.get_result = Method(o=self.fu_layouts.accept)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        rob_block_interrupts = self.gen_params.get(DependencyManager).get_dependency(ROBBlockInterruptsKey())

        v_freerf = SuperscalarFreeRF(self.v_params.vrp_count, 1, reset_state=2**self.v_params.vrl_count - 1)
        v_frat = FRAT(gen_params=self.gen_params, superscalarity=2, zero_init=False)
        v_rrat = RRAT(gen_params=self.gen_params, zero_init=False)

        v_retirement = VectorRetirement(
            self.gen_params, self.v_params.vrp_count, v_rrat.commit, v_freerf.deallocates[0]
        )
        announcer = VectorAnnouncer(self.gen_params, 3)

        backend = VectorBackend(self.gen_params, announcer.announce_list[0], v_retirement.report_end)
        fifo_to_vvrs = BasicFifo(self.v_frontend_layouts.instr_to_vvrs, 2)
        fifo_to_mem = BasicFifo(self.v_frontend_layouts.instr_to_mem, 2)
        frontend = VectorFrontend(
            self.gen_params,
            rob_block_interrupts,
            announcer.announce_list[1],
            announcer.announce_list[2],
            backend.report_mult,
            v_freerf.allocate,
            v_frat.get_rename_list[0],
            v_frat.get_rename_list[1],
            v_frat.set_rename_list[0],
            fifo_to_mem.write,
            fifo_to_vvrs.write,
            backend.initialise_regs,
        )
        connect_data_to_vvrs = ConnectTrans(fifo_to_vvrs.read, backend.put_instr)

        self.precommit.proxy(m, v_retirement.precommit)
        self.get_result.proxy(m, announcer.accept)
        self.insert.proxy(m, frontend.insert)
        self.select.proxy(m, frontend.select)
        self.update.proxy(m, frontend.update)

        m.submodules.v_freerf = v_freerf
        m.submodules.v_frat = v_frat
        m.submodules.v_rrat = v_rrat
        m.submodules.v_retirement = v_retirement
        m.submodules.announcer = announcer
        m.submodules.backend = backend
        m.submodules.fifo_to_vvrs = fifo_to_vvrs
        m.submodules.fifo_to_mem = fifo_to_mem
        m.submodules.frontend = frontend
        m.submodules.connect_data_to_vvrs = connect_data_to_vvrs

        return m


@dataclass(frozen=True)
class VectorBlockComponent(BlockComponentParams):
    rs_entries: int

    def get_module(self, gen_params: GenParams) -> FuncBlock:
        gen_params.v_params.vxrs_entries = self.rs_entries
        unit = VectorCore(gen_params)
        connections = gen_params.get(DependencyManager)
        connections.add_dependency(InstructionPrecommitKey(), unit.precommit)
        return unit

    def get_optypes(self) -> set[OpType]:
        return {OpType.V_ARITHMETIC, OpType.V_CONTROL}

    def get_rs_entry_count(self) -> int:
        return self.rs_entries
