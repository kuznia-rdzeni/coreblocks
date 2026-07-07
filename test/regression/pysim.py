import re
import os
import logging

from amaranth.utils import exact_log2
from amaranth import *

from transactron.core.keys import TransactionManagerKey
from transactron.profiler import Profile
from transactron.testing.tick_count import make_tick_count_process

from .memory import *
from .common import SimulationBackend, SimulationExecutionResult

from transactron.testing import (
    PysimSimulator,
    profiler_process,
    make_logging_process,
    parse_logging_level,
    TestbenchContext,
    ProcessContext,
)
from transactron.testing.evlog import capture_evlog
from transactron.utils.dependencies import DependencyContext, DependencyManager
from transactron.lib.metrics import HardwareMetricsManager
from ..peripherals.test_wishbone import WishboneInterfaceWrapper

from coreblocks.core import Core
from coreblocks.socks.socks import Socks
from coreblocks.params import GenParams
from coreblocks.params import configurations


class PySimulation(SimulationBackend):
    def __init__(self, traces_file: Optional[str] = None, with_socks: bool = False, reset_pc: Optional[int] = None):
        conf = configurations.full
        if reset_pc is not None:
            conf = conf.replace(start_pc=reset_pc)
        self.gp = GenParams(conf)
        self.running = False
        self.cycle_cnt = 0
        self.traces_file = traces_file
        self.with_socks = with_socks

        self.log_level = parse_logging_level(os.environ["__TRANSACTRON_LOG_LEVEL"])
        self.log_filter = os.environ["__TRANSACTRON_LOG_FILTER"]

        self.metrics_manager = HardwareMetricsManager()

    def _wishbone_slave(
        self, mem_model: CoreMemoryModel, wb_ctrl: WishboneInterfaceWrapper, is_instr_bus: bool, delay: int = 0
    ):
        async def f(sim: TestbenchContext):
            while True:
                await wb_ctrl.slave_wait(sim)

                word_width_bytes = self.gp.isa.xlen // 8

                # Wishbone is addressing words, so we need to shift it a bit to get the real address.
                addr = sim.get(wb_ctrl.wb.adr) << exact_log2(word_width_bytes)
                sel = sim.get(wb_ctrl.wb.sel)
                dat_w = sim.get(wb_ctrl.wb.dat_w)

                resp_data = 0

                if sim.get(wb_ctrl.wb.we):
                    resp = mem_model.write(
                        WriteRequest(addr=addr, data=dat_w, byte_count=word_width_bytes, byte_sel=sel)
                    )
                else:
                    resp = mem_model.read(
                        ReadRequest(
                            addr=addr,
                            byte_count=word_width_bytes,
                            byte_sel=sel,
                            exec=is_instr_bus,
                        )
                    )
                    resp_data = resp.data

                ack = err = rty = 0
                match resp.status:
                    case ReplyStatus.OK:
                        ack = 1
                    case ReplyStatus.ERROR:
                        err = 1
                    case ReplyStatus.RETRY:
                        rty = 1

                for _ in range(delay):
                    await sim.tick()

                await wb_ctrl.slave_respond(sim, resp_data, ack=ack, err=err, rty=rty)

        return f

    def _waiter(self, on_finish: Callable[[TestbenchContext], None]):
        async def f(sim: TestbenchContext):
            while self.running:
                self.cycle_cnt += 1
                await sim.tick()

            on_finish(sim)

        return f

    def pretty_dump_metrics(self, metric_values: dict[str, dict[str, int]], filter_regexp: str = ".*"):
        str = "=== Core metrics dump ===\n"

        put_space_before = True
        for metric_name in sorted(metric_values.keys()):
            if not re.search(filter_regexp, metric_name):
                continue

            metric = self.metrics_manager.get_metrics()[metric_name]

            if metric.description != "":
                if not put_space_before:
                    str += "\n"

                str += f"# {metric.description}\n"

            for reg in metric.regs.values():
                reg_value = metric_values[metric_name][reg.name]

                desc = f" # {reg.description} [reg width={reg.width}]"
                str += f"{metric_name}/{reg.name} {reg_value}{desc}\n"

            put_space_before = False
            if metric.description != "":
                str += "\n"
                put_space_before = True

        logging.info(str)

    async def run(
        self,
        mem_model: CoreMemoryModel,
        timeout_cycles: int = 5000,
        get_interrupt_value: Optional[Callable[[], int]] = None,
    ) -> SimulationExecutionResult:
        with DependencyContext(DependencyManager()):
            core = Core(gen_params=self.gp)

            if self.with_socks:
                core = Socks(core, core_gen_params=self.gp)

            wb_instr_ctrl = WishboneInterfaceWrapper(core.wb_instr)
            wb_data_ctrl = WishboneInterfaceWrapper(core.wb_data)

            self.running = True
            self.cycle_cnt = 0

            sim = PysimSimulator(core, max_cycles=timeout_cycles, traces_file=self.traces_file)
            if get_interrupt_value is not None:

                async def interrupt_generator_process(sim: ProcessContext):
                    while True:
                        sim.set(core.interrupts, get_interrupt_value())
                        await sim.tick()

                sim.add_process(interrupt_generator_process)

            sim.add_testbench(self._wishbone_slave(mem_model, wb_instr_ctrl, is_instr_bus=True), background=True)
            sim.add_testbench(self._wishbone_slave(mem_model, wb_data_ctrl, is_instr_bus=False), background=True)

            def on_error():
                raise RuntimeError("Simulation finished due to an error")

            sim.add_process(make_logging_process(self.log_level, self.log_filter, on_error))
            sim.add_process(make_tick_count_process())

            # This enables logging in benchmarks. TODO: after unifying regression testing, remove.
            logging.basicConfig()
            logging.getLogger().setLevel(self.log_level)

            profile = None
            if "__TRANSACTRON_PROFILE" in os.environ:
                transaction_manager = DependencyContext.get().get_dependency(TransactionManagerKey())
                profile = Profile()
                sim.add_process(profiler_process(transaction_manager, profile))

            evlog = None
            if "__TRANSACTRON_EVLOG" in os.environ:
                evlog, evlog_process = capture_evlog()
                if evlog.schema.sites:
                    sim.add_process(evlog_process)
                else:  # the design was elaborated without the event log enabled
                    evlog = None

            metric_values: dict[str, dict[str, int]] = {}

            def on_sim_finish(sim: TestbenchContext):
                # Collect metric values before we finish the simulation
                for metric_name, metric in self.metrics_manager.get_metrics().items():
                    metric = self.metrics_manager.get_metrics()[metric_name]
                    metric_values[metric_name] = {}
                    for reg_name in metric.regs:
                        metric_values[metric_name][reg_name] = sim.get(
                            self.metrics_manager.get_register_value(metric_name, reg_name)
                        )

            sim.add_testbench(self._waiter(on_finish=on_sim_finish))
            sim.run()
            success = True  # timeout throws an exception in sim

            self.pretty_dump_metrics(metric_values)

            return SimulationExecutionResult(success, metric_values, profile, evlog)

    def stop(self):
        self.running = False
