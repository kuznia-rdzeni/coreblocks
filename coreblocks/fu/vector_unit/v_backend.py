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
from coreblocks.fu.vector_unit.v_execution_ender import *
from coreblocks.fu.vector_unit.v_executor import *

# TODO optimise by allowing to start porcessing new register while old is still being uploaded
# TODO - downloader should download v0 from address//8
# TODO - initialize regs somewhere
# TODO - handle rp_dst == RegisterType.X
# TODO - handle tail undisturbed elements

__all__ = ["VectorBackend"]


class VectorBackend(Elaboratable):
    """Vector unit backend

    This module is responsible for executing vector instructions which were processed by the VectorFrontend.
    The processed instructions are placed in the VVRS, where they wait until all operands are ready. The readiness
    of the operands is tracked by a scoreboard, which is updated on issuing and completing of each instructions.
    The VVRS inserter listens for `update`\\s to implement the forwarding of the readiness of instructions that
    have been completed.

    Ready instructions are read out of order and sent to `VectorExecutor`\\s for execution. Each `VectorExecutor`
    informs the `VectorExecutionEnder` when it has finished processing the instruction. When all executors have
    finished processing `VectorExecutionEnder` updates the scoreboard, the VVRS and informs `VectorRetirement`
    and `VectorAnnouncer` about this fact.

    Attributes
    ----------
    put_instr : Method
        The method to insert instructions from the vector frontend.
    initialise_regs : list[Method]
        List with one method for each register, to initialise it on allocation.
    vrf_write : list[Method]
        List with one method for each register bank, to write data into it.
    vrf_read_req : list[Method]
        List with one method for each register bank, to request data to be read from it.
    vrf_read_resp : list[Method]
        List with one method for each register bank, to read requested data.
    v_update : Method
        The method to call to indicate that a vector register is ready.
    scoreboard_get_dirty : Method
        The method to check if the register is already ready.
    scoreboard_set_dirty : Method
        The method for setting the dirty bit for the register to indicate that it's not ready
        and that there are no results yet.
    """

    def __init__(self, gen_params: GenParams, announce: Method, report_end: Method, v_update_methods : list[Method] =[]):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        announce : Method
            The method called when an instruction has been processed, to forward that information to the
            scalar core.
        report_end : Method
            Used to report the end of instruction execution to `VectorRetirement`.
        v_update_methods : list[Method]
            Methods to be called with vector register updates.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.announce = announce
        self.report_end = report_end
        self.v_update_methods = v_update_methods

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.v_params.vvrs_entries_bits)
        self.vreg_layout = VectorRegisterBankLayouts(self.gen_params)
        self.alu_layouts = VectorAluLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)
        self.scoreboard_layout = ScoreboardLayouts(self.v_params.vrp_count)

        self.put_instr = Method(i=self.layouts.vvrs_in)
        self.initialise_regs = [Method(i=self.vreg_layout.initialise) for _ in range(self.v_params.vrp_count)]
        self.report_mult = Method(i=self.layouts.ender_report_mult)
        self.vrf_write = [Method(i=self.vrf_layout.write) for _ in range(self.v_params.register_bank_count)]
        self.vrf_read_req = [Method(i=self.vrf_layout.read_req) for _ in range(self.v_params.register_bank_count)]
        self.vrf_read_resp = [Method(o=self.vrf_layout.read_resp_o) for _ in range(self.v_params.register_bank_count)]
        self.scoreboard_get_dirty = Method(i=self.scoreboard_layout.get_dirty_in, o = self.scoreboard_layout.get_dirty_out)
        self.scoreboard_set_dirty = Method(i=self.scoreboard_layout.set_dirty_in)
        self.v_update = Method(i = self.vvrs_layouts.update_in)
        
    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.ready_scoreboard = ready_scoreboard = Scoreboard(
            self.v_params.vrp_count, superscalarity=5, data_forward=False
        )
        m.submodules.vvrs = vvrs = VVRS(self.gen_params, self.v_params.vvrs_entries)
        m.submodules.insert_to_vvrs = insert_to_vvrs = VectorInsertToVVRS(
            self.gen_params,
            vvrs.select,
            vvrs.insert,
            ready_scoreboard.get_dirty_list[:4],
            ready_scoreboard.set_dirty_list[0],
        )
        self.scoreboard_get_dirty.proxy(m, ready_scoreboard.get_dirty_list[4])
        self.scoreboard_set_dirty.proxy(m, ready_scoreboard.set_dirty_list[1])

        self.put_instr.proxy(m, insert_to_vvrs.issue)

        m.submodules.update_product = update_product = MethodProduct([vvrs.update, insert_to_vvrs.update] + self.v_update_methods)
        self.v_update.proxy(m, update_product.method)
        m.submodules.ender = ender = VectorExecutionEnder(
            self.gen_params, self.announce, self.v_update, ready_scoreboard.set_dirty_list[2], self.report_end
        )
        self.report_mult.proxy(m, ender.report_mult)
        executors = [
            VectorExecutor(self.gen_params, i, ender.end_list[i]) for i in range(self.v_params.register_bank_count)
        ]
        m.submodules.executors = ModuleConnector(*executors)

        m.submodules.connect_init_ender = connect_init_ender = Connect(self.layouts.executor_in)
        with Transaction(name="backend_init_ender").body(m):
            instr = connect_init_ender.read(m)
            ender.init(m, rp_dst=instr.rp_dst, rob_id=instr.rob_id)

        m.submodules.input_product = input_product = MethodProduct(
            [executor.issue for executor in executors] + [connect_init_ender.write]
        )
        m.submodules.wakeup_select = WakeupSelect(
            gen_params=self.gen_params,
            get_ready=vvrs.get_ready_list[0],
            take_row=vvrs.take,
            issue=input_product.method,
            row_layout=self.layouts.vvrs_out,
        )

        connect_init_banks_list = []
        for i in range(self.v_params.vrp_count):
            init_banks_list = [executor.initialise_regs[i] for executor in executors]
            connect_init_banks_list.append(MethodProduct(init_banks_list))
            self.initialise_regs[i].proxy(m, connect_init_banks_list[-1].method)
        for i, executor in enumerate(executors):
            self.vrf_write[i].proxy(m, executor.write_vrf)
            self.vrf_read_req[i].proxy(m, executor.read_req)
            self.vrf_read_resp[i].proxy(m, executor.read_resp)
        m.submodules.connect_init_banks = ModuleConnector(*connect_init_banks_list)

        return m
