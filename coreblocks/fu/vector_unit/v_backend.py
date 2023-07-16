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
    def __init__(self, gen_params: GenParams, announce : Method, report_end : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.announce = announce
        self.report_end = report_end

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.v_params.vvrs_entries_bits)
        self.vreg_layout = VectorRegisterBankLayouts(self.gen_params)
        self.alu_layouts = VectorAluLayouts(self.gen_params)

        self.put_instr = Method(i=self.layouts.vvrs_in)
        self.initialise_regs = [Method(i = self.vreg_layout.initialise) for _ in range(self.v_params.vrp_count)]
        self.report_mult = Method(i=self.layouts.ender_report_mult)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.ready_scoreboard = ready_scoreboard = Scoreboard(self.v_params.vrp_count, superscalarity = 4)
        m.submodules.vvrs = vvrs = VVRS(self.gen_params, self.v_params.vvrs_entries_bits)
        m.submodules.insert_to_vvrs = insert_to_vvrs = VectorInsertToVVRS(self.gen_params, vvrs.select, vvrs.insert, ready_scoreboard.get_dirty_list, ready_scoreboard.set_dirty_list[0])
        
        self.put_instr.proxy(m, insert_to_vvrs.issue)

        m.submodules.ender = ender = VectorExecutionEnder(self.gen_params, self.announce, vvrs.update, ready_scoreboard.set_dirty_list[1], self.report_end)
        self.report_mult.proxy(m, ender.report_mult)
        executors = [VectorExecutor(self.gen_params, i, ender.end_list[i]) for i in range(self.v_params.register_bank_count)]
        m.submodules.executors = ModuleConnector(*executors)

        m.submodules.connect_init_ender = connect_init_ender = Connect(self.layouts.executor_in)
        with Transaction(name="backend_init_ender").body(m):
            instr = connect_init_ender.read(m)
            ender.init(m, rp_dst = instr.rp_dst, rob_id = instr.rob_id)

        m.submodules.input_product = input_product = MethodProduct([executor.issue for executor in executors] + [connect_init_ender.write])
        m.submodules.wakeup_select = wakeup_select = WakeupSelect(gen_params = self.gen_params, get_ready = vvrs.get_ready_list[0], take_row = vvrs.take, issue = input_product.method, row_layout = self.layouts.vvrs_out)

        connect_init_banks_list = []
        for i in range(self.v_params.vrp_count):
            init_banks_list = [executor.initialise_regs[i] for executor in executors]
            connect_init_banks_list.append(MethodProduct(init_banks_list))
            self.initialise_regs[i].proxy(m, connect_init_banks_list[-1].method)
        m.submodules.connect_init_banks = ModuleConnector(*connect_init_banks_list)


        return m
