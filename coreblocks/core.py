from amaranth import *
from amaranth.lib.wiring import Component, flipped, connect, In, Out
from transactron.lib.allocators import PriorityEncoderAllocator

from transactron.utils.dependencies import DependencyContext
from coreblocks.priv.traps.instr_counter import CoreInstructionCounter
from coreblocks.func_blocks.interface.func_blocks_unifier import FuncBlocksUnifier
from coreblocks.priv.traps.interrupt_controller import ISA_RESERVED_INTERRUPTS, InternalInterruptController
from transactron.core import TModule, Method, def_method
from transactron.lib import CrossbarConnectTrans
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import (
    CSRInstancesKey,
    CommonBusDataKey,
)
from coreblocks.params.genparams import GenParams
from coreblocks.core_structs.crat import CheckpointRAT
from coreblocks.core_structs.rat import RRAT
from coreblocks.core_structs.rob import ReorderBuffer
from coreblocks.core_structs.rf import RegisterFile
from coreblocks.priv.csr.csr_instances import CSRInstances
from coreblocks.frontend.frontend import CoreFrontend
from coreblocks.priv.traps.exception import ExceptionInformationRegister
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.backend.announcement import ResultAnnouncement
from coreblocks.backend.retirement import Retirement
from coreblocks.peripherals.bus_adapter import WishboneMasterAdapter
from coreblocks.peripherals.wishbone import WishboneMaster, WishboneInterface
from transactron.lib.metrics import HwMetricsEnabledKey

__all__ = ["Core"]


class Core(Component):
    wb_instr: WishboneInterface
    wb_data: WishboneInterface
    interrupts: Signal

    def __init__(self, *, gen_params: GenParams):
        super().__init__(
            {
                "wb_instr": Out(WishboneInterface(gen_params.wb_params).signature),
                "wb_data": Out(WishboneInterface(gen_params.wb_params).signature),
                "interrupts": In(ISA_RESERVED_INTERRUPTS + gen_params.interrupt_custom_count),
            }
        )

        self.gen_params = gen_params

        self.dm = DependencyContext.get()
        if self.gen_params.debug_signals_enabled:
            self.dm.add_dependency(HwMetricsEnabledKey(), True)

        self.wb_master_instr = WishboneMaster(self.gen_params.wb_params, "instr")
        self.wb_master_data = WishboneMaster(self.gen_params.wb_params, "data")

        self.bus_master_instr_adapter = WishboneMasterAdapter(self.wb_master_instr)
        self.bus_master_data_adapter = WishboneMasterAdapter(self.wb_master_data)
        self.dm.add_dependency(CommonBusDataKey(), self.bus_master_data_adapter)

        self.frontend = CoreFrontend(gen_params=self.gen_params, instr_bus=self.bus_master_instr_adapter)

        self.rf_allocator = PriorityEncoderAllocator(
            gen_params.phys_regs, gen_params.frontend_superscalarity, init=2**gen_params.phys_regs - 2
        )

        self.CRAT = CheckpointRAT(gen_params=self.gen_params)
        self.RRAT = RRAT(gen_params=self.gen_params)
        self.RF = RegisterFile(
            gen_params=self.gen_params,
            read_ports=2 * self.gen_params.frontend_superscalarity,
            write_ports=self.gen_params.announcement_superscalarity,
            free_ports=1,
        )
        self.ROB = ReorderBuffer(
            gen_params=self.gen_params, mark_done_ports=self.gen_params.announcement_superscalarity
        )

        self.retirement = Retirement(self.gen_params)

        self.exception_information_register = ExceptionInformationRegister(
            self.gen_params,
            rob_get_indices=self.ROB.get_indices,
            fetch_stall_exception=self.frontend.stall,
        )

        self.func_blocks_unifier = FuncBlocksUnifier(
            gen_params=gen_params,
            blocks=gen_params.func_units_config,
        )

        self.csr_instances = CSRInstances(self.gen_params)
        self.dm.add_dependency(CSRInstancesKey(), self.csr_instances)

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

        m.submodules.rf_allocator = rf_allocator = self.rf_allocator
        m.submodules.CRAT = crat = self.CRAT
        m.submodules.RRAT = rrat = self.RRAT
        m.submodules.RF = rf = self.RF
        m.submodules.rob = rob = self.ROB

        m.submodules.csr_instances = self.csr_instances
        m.submodules.interrupt_controller = self.interrupt_controller
        m.d.comb += self.interrupt_controller.internal_report_level.eq(self.interrupts[0:16])
        m.d.comb += self.interrupt_controller.custom_report.eq(self.interrupts[16:])

        m.submodules.core_counter = core_counter = CoreInstructionCounter(self.gen_params)

        get_instr = Method.like(self.frontend.consume_instr)

        @def_method(m, get_instr)
        def _():
            ret = self.frontend.consume_instr(m)
            core_counter.increment(m, ret.count)
            return ret

        m.submodules.scheduler = scheduler = Scheduler(gen_params=self.gen_params)
        scheduler.get_instr.provide(get_instr)
        scheduler.get_free_reg.provide(rf_allocator.alloc)
        scheduler.crat_commit_checkpoint.provide(crat.commit_checkpoint)
        scheduler.crat_rename.provide(crat.rename)
        scheduler.crat_tag.provide(crat.tag)
        scheduler.crat_active_tags.provide(crat.get_active_tags)
        scheduler.rob_put.provide(rob.put)
        scheduler.rf_read_req.provide(rf.read_req)
        scheduler.rf_read_resp.provide(rf.read_resp)
        for i, block in enumerate(self.func_blocks_unifier.rs_blocks):
            scheduler.rs_select[i].provide(block.select)
            scheduler.rs_insert[i].provide(block.insert)

        m.submodules.exception_information_register = self.exception_information_register

        announce_result: list[Method] = []
        for i in range(self.gen_params.announcement_superscalarity):
            m.submodules[f"announcement_{i}"] = announcement = ResultAnnouncement(gen_params=self.gen_params)
            announcement.rob_mark_done.provide(self.ROB.mark_done[i])
            announcement.rs_update.provide(self.func_blocks_unifier.update[i])
            announcement.rf_write_val.provide(self.RF.write[i])
            announce_result.append(announcement.push_result)

        m.submodules.announcement_connector = CrossbarConnectTrans.create(
            self.func_blocks_unifier.get_result, announce_result
        )

        m.submodules.retirement = retirement = self.retirement
        retirement.rob_peek.provide(rob.peek)
        retirement.rob_retire.provide(rob.retire)
        retirement.r_rat_commit.provide(rrat.commit)
        retirement.r_rat_peek.provide(rrat.peek)
        retirement.free_rf_put.provide(rf_allocator.free[0])
        retirement.rf_free.provide(rf.free[0])
        retirement.exception_cause_get.provide(self.exception_information_register.get)
        retirement.exception_cause_clear.provide(self.exception_information_register.clear)
        retirement.c_rat_restore.provide(crat.flush_restore)
        retirement.fetch_continue.provide(self.frontend.resume_from_exception)
        retirement.instr_decrement.provide(core_counter.decrement)
        retirement.trap_entry.provide(self.interrupt_controller.entry)
        retirement.async_interrupt_cause.provide(self.interrupt_controller.interrupt_cause)
        retirement.checkpoint_get_active_tags.provide(crat.get_active_tags)
        retirement.checkpoint_tag_free.provide(crat.free_tag)

        m.submodules.func_blocks_unifier = self.func_blocks_unifier

        return m
