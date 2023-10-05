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
    """Vector functional block

    This is the top level module, that connects all the parts that create a vector
    processing unit.

    Instructions from the scalar core are inserted into the scalar RS, where they wait until
    all scalar operands are ready. They are then processed by the `VectorFrontend`
    which handles vector status CSR's, rename and allocate physical registers. The
    instructions are passed to the `VectorBackend` where they are executed. `VectorAnnouncer`
    is used to pass information that the instruction has finished execution to the scalar core, and
    `VectorRetirement` listen for incomming `precommit` calls, to release vector
    internal resources on vector instruction retirement.

    Attributes
    ----------
    insert : Method
        Insert the instruction to RS.
    select : Method
        Get the id of a free RS entry.
    update : Method
        Called to inform about the change of the scalar register status.
    precommit : Method
        An notification from retirement, about currently committed instructions.
    get_result : Method
        The method used by the scalar core, to get information that an instruction
        has finished the execution.
    """

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.vxrs_layouts = VectorXRSLayout(
            self.gen_params, rs_entries_bits=log2_int(self.v_params.vxrs_entries, False)
        )
        self.x_retirement_layouts = gen_params.get(RetirementLayouts)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.v_frontend_layouts = VectorFrontendLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)
        self.scoreboard_layout = ScoreboardLayouts(self.v_params.vrp_count)

        self.insert = Method(i=self.vxrs_layouts.insert_in)
        self.select = Method(o=self.vxrs_layouts.select_out)
        self.update = Method(i=self.vxrs_layouts.update_in)
        self.precommit = Method(i=self.x_retirement_layouts.precommit)
        self.get_result = Method(o=self.fu_layouts.accept)

        self.vrf_write = [
            Method(i=self.vrf_layout.write, name=f"vrf_write{i}") for i in range(self.v_params.register_bank_count)
        ]
        self.vrf_read_req = [
            Method(i=self.vrf_layout.read_req, name=f"vrf_read_req{i}")
            for i in range(self.v_params.register_bank_count)
        ]
        self.vrf_read_resp = [
            Method(o=self.vrf_layout.read_resp_o, name=f"vrf_read_resp{i}")
            for i in range(self.v_params.register_bank_count)
        ]
        self.scoreboard_get_dirty = Method(
            i=self.scoreboard_layout.get_dirty_in, o=self.scoreboard_layout.get_dirty_out
        )
        self.scoreboard_set_dirty = Method(i=self.scoreboard_layout.set_dirty_in)

        self.connections = self.gen_params.get(DependencyManager)
        self.connections.add_dependency(VectorFrontendInsertKey(), self.insert)
        self.connections.add_dependency(VectorVRFAccessKey(), (self.vrf_write, self.vrf_read_req, self.vrf_read_resp))
        self.connections.add_dependency(VectorScoreboardKey(), (self.scoreboard_get_dirty, self.scoreboard_set_dirty))

    def elaborate(self, platform) -> TModule:
        m = TModule()

        rob_block_interrupts = self.connections.get_dependency(ROBBlockInterruptsKey())

        v_freerf = SuperscalarFreeRF(self.v_params.vrp_count, 1, reset_state=2**self.v_params.vrl_count - 1)
        v_frat = FRAT(gen_params=self.gen_params, superscalarity=2, zero_init=False)
        v_rrat = RRAT(gen_params=self.gen_params, zero_init=False)

        v_retirement = VectorRetirement(
            self.gen_params, self.v_params.vrp_count, v_rrat.commit, v_freerf.deallocates[0]
        )
        announcer = VectorAnnouncer(self.gen_params, 4)
        vlsu = self.connections.get_dependency(VectorLSUKey())

        backend = VectorBackend(self.gen_params, announcer.announce_list[0], v_retirement.report_end, [vlsu.update_v])
        fifo_to_vvrs = BasicFifo(self.v_frontend_layouts.instr_to_vvrs, 2)
        frontend = VectorFrontend(
            self.gen_params,
            rob_block_interrupts,
            announcer.announce_list[1],
            announcer.announce_list[2],
            v_freerf.allocate,
            v_frat.get_rename_list[0],
            v_frat.get_rename_list[1],
            v_frat.set_rename_list[0],
            vlsu.insert_v,
            fifo_to_vvrs.write,
            backend.initialise_regs,
        )
        connect_data_to_vvrs = ConnectTrans(fifo_to_vvrs.read, backend.put_instr)
        connect_mem_result = ConnectTrans(vlsu.get_result_v, announcer.announce_list[3])
        with Transaction(name="vlsu_get_result_v_trans").body(m):
            data = vlsu.get_result_v(m)
            announcer.announce_list[3](m, data)
            v_retirement.report_end(m, rob_id=data.rob_id, rp_dst=data.rp_dst)
            backend.v_update(m, tag=data.rp_dst, value=0)

        self.precommit.proxy(m, v_retirement.precommit)
        self.get_result.proxy(m, announcer.accept)
        self.insert.proxy(m, frontend.insert)
        self.select.proxy(m, frontend.select)
        self.update.proxy(m, frontend.update)
        self.scoreboard_get_dirty.proxy(m, backend.scoreboard_get_dirty)
        self.scoreboard_set_dirty.proxy(m, backend.scoreboard_set_dirty)

        for i in range(len(backend.vrf_write)):
            self.vrf_write[i].proxy(m, backend.vrf_write[i])
            self.vrf_read_req[i].proxy(m, backend.vrf_read_req[i])
            self.vrf_read_resp[i].proxy(m, backend.vrf_read_resp[i])

        m.submodules.v_freerf = v_freerf
        m.submodules.v_frat = v_frat
        m.submodules.v_rrat = v_rrat
        m.submodules.v_retirement = v_retirement
        m.submodules.announcer = announcer
        m.submodules.backend = backend
        m.submodules.fifo_to_vvrs = fifo_to_vvrs
        m.submodules.frontend = frontend
        m.submodules.connect_data_to_vvrs = connect_data_to_vvrs
        m.submodules.connect_mem_result = connect_mem_result

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
