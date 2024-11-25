from amaranth import *
from amaranth.lib.wiring import Component, flipped, connect, In, Out
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector

from transactron.utils.dependencies import DependencyContext
from coreblocks.priv.traps.instr_counter import CoreInstructionCounter
from coreblocks.func_blocks.interface.func_blocks_unifier import FuncBlocksUnifier
from coreblocks.priv.traps.interrupt_controller import ISA_RESERVED_INTERRUPTS, InternalInterruptController
from transactron.core import Transaction, TModule
from transactron.lib import ConnectTrans, MethodProduct
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import (
    FetchResumeKey,
    CSRInstancesKey,
    CommonBusDataKey,
)
from coreblocks.params.genparams import GenParams
from coreblocks.core_structs.rat import FRAT, RRAT
from coreblocks.core_structs.rob import ReorderBuffer
from coreblocks.core_structs.rf import RegisterFile
from coreblocks.priv.csr.csr_instances import GenericCSRRegisters
from coreblocks.frontend.frontend import CoreFrontend
from coreblocks.priv.traps.exception import ExceptionInformationRegister
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.backend.annoucement import ResultAnnouncement
from coreblocks.backend.retirement import Retirement
from coreblocks.peripherals.bus_adapter import WishboneMasterAdapter
from coreblocks.peripherals.wishbone import WishboneMaster, WishboneInterface, WishboneSignature
from transactron.lib import BasicFifo
from transactron.lib.metrics import HwMetricsEnabledKey

__all__ = ["Core"]


class Core(Component):
    wb_instr: WishboneInterface
    wb_data: WishboneInterface
    interrupts: Signal

    def __init__(self, *, gen_params: GenParams):
        super().__init__(
            {
                "wb_instr": Out(WishboneSignature(gen_params.wb_params)),
                "wb_data": Out(WishboneSignature(gen_params.wb_params)),
                "interrupts": In(ISA_RESERVED_INTERRUPTS + gen_params.interrupt_custom_count),
            }
        )

        self.gen_params = gen_params

        self.connections = DependencyContext.get()
        if self.gen_params.debug_signals_enabled:
            self.connections.add_dependency(HwMetricsEnabledKey(), True)

        self.wb_master_instr = WishboneMaster(self.gen_params.wb_params, "instr")
        self.wb_master_data = WishboneMaster(self.gen_params.wb_params, "data")

        self.bus_master_instr_adapter = WishboneMasterAdapter(self.wb_master_instr)
        self.bus_master_data_adapter = WishboneMasterAdapter(self.wb_master_data)

        self.frontend = CoreFrontend(gen_params=self.gen_params, instr_bus=self.bus_master_instr_adapter)

        self.free_rf_fifo = BasicFifo(
            self.gen_params.get(SchedulerLayouts).free_rf_layout, 2**self.gen_params.phys_regs_bits
        )

        self.FRAT = FRAT(gen_params=self.gen_params)
        self.RRAT = RRAT(gen_params=self.gen_params)
        self.RF = RegisterFile(gen_params=self.gen_params)
        self.ROB = ReorderBuffer(gen_params=self.gen_params)

        self.connections.add_dependency(CommonBusDataKey(), self.bus_master_data_adapter)

        self.exception_information_register = ExceptionInformationRegister(
            self.gen_params,
            rob_get_indices=self.ROB.get_indices,
            fetch_stall_exception=self.frontend.stall,
        )

        self.func_blocks_unifier = FuncBlocksUnifier(
            gen_params=gen_params,
            blocks=gen_params.func_units_config,
        )

        self.announcement = ResultAnnouncement(
            gen_params=self.gen_params,
            get_result=self.func_blocks_unifier.get_result,
            rob_mark_done=self.ROB.mark_done,
            rs_update=self.func_blocks_unifier.update,
            rf_write=self.RF.write,
        )

        self.csr_generic = GenericCSRRegisters(self.gen_params)
        self.connections.add_dependency(CSRInstancesKey(), self.csr_generic)

        self.interrupt_controller = InternalInterruptController(self.gen_params)

    def elaborate(self, platform):
        m = TModule()

        connect(m.top_module, flipped(self.wb_instr), self.wb_master_instr.wb_master)
        connect(m.top_module, flipped(self.wb_data), self.wb_master_data.wb_master)

        m.submodules.wb_master_instr = self.wb_master_instr
        m.submodules.wb_master_data = self.wb_master_data

        m.submodules.bus_master_instr_adapter = self.bus_master_instr_adapter
        m.submodules.bus_master_data_adapter = self.bus_master_data_adapter

        m.submodules.frontend = self.frontend

        m.submodules.free_rf_fifo = free_rf_fifo = self.free_rf_fifo
        m.submodules.FRAT = frat = self.FRAT
        m.submodules.RRAT = rrat = self.RRAT
        m.submodules.RF = rf = self.RF
        m.submodules.ROB = rob = self.ROB

        m.submodules.csr_generic = self.csr_generic
        m.submodules.interrupt_controller = self.interrupt_controller
        m.d.comb += self.interrupt_controller.internal_report_level.eq(self.interrupts[0:16])
        m.d.comb += self.interrupt_controller.custom_report.eq(self.interrupts[16:])

        m.submodules.core_counter = core_counter = CoreInstructionCounter(self.gen_params)

        drop_second_ret_value = (self.gen_params.get(DecodeLayouts).decoded_instr, lambda _, rets: rets[0])
        m.submodules.get_instr = get_instr = MethodProduct(
            [self.frontend.consume_instr, core_counter.increment], combiner=drop_second_ret_value
        )

        m.submodules.scheduler = Scheduler(
            get_instr=get_instr.method,
            get_free_reg=free_rf_fifo.read,
            rat_rename=frat.rename,
            rob_put=rob.put,
            rf_read1=rf.read1,
            rf_read2=rf.read2,
            reservation_stations=self.func_blocks_unifier.rs_blocks,
            gen_params=self.gen_params,
        )

        m.submodules.exception_information_register = self.exception_information_register

        fetch_resume = self.connections.get_optional_dependency(FetchResumeKey())
        if fetch_resume is not None:
            fetch_resume_fb, fetch_resume_unifiers = fetch_resume
            m.submodules.fetch_resume_unifiers = ModuleConnector(**fetch_resume_unifiers)

            m.submodules.fetch_resume_connector = ConnectTrans(fetch_resume_fb, self.frontend.resume_from_unsafe)

        m.submodules.announcement = self.announcement
        m.submodules.func_blocks_unifier = self.func_blocks_unifier
        m.submodules.retirement = Retirement(
            self.gen_params,
            rob_peek=rob.peek,
            rob_retire=rob.retire,
            r_rat_commit=rrat.commit,
            r_rat_peek=rrat.peek,
            free_rf_put=free_rf_fifo.write,
            rf_free=rf.free,
            exception_cause_get=self.exception_information_register.get,
            exception_cause_clear=self.exception_information_register.clear,
            frat_rename=frat.rename,
            fetch_continue=self.frontend.resume_from_exception,
            instr_decrement=core_counter.decrement,
            trap_entry=self.interrupt_controller.entry,
            async_interrupt_cause=self.interrupt_controller.interrupt_cause,
        )

        # push all registers to FreeRF at reset. r0 should be skipped, stop when counter overflows to 0
        free_rf_reg = Signal(self.gen_params.phys_regs_bits, init=1)
        with Transaction(name="InitFreeRFFifo").body(m, request=(free_rf_reg.bool())):
            free_rf_fifo.write(m, free_rf_reg)
            m.d.sync += free_rf_reg.eq(free_rf_reg + 1)

        return m
