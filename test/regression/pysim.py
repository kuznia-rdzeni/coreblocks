import re
import os
import logging

from amaranth.sim import Passive, Settle
from amaranth.utils import exact_log2
from amaranth import *

from transactron.core.keys import TransactionManagerKey

from .memory import *
from .common import SimulationBackend, SimulationExecutionResult

from transactron.testing import (
    PysimSimulator,
    TestGen,
    profiler_process,
    Profile,
    make_logging_process,
    parse_logging_level,
)
from transactron.utils.dependencies import DependencyContext, DependencyManager
from transactron.lib.metrics import HardwareMetricsManager
from ..peripherals.test_wishbone import WishboneInterfaceWrapper

from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.params.configurations import full_core_config


class PySimulation(SimulationBackend):
    def __init__(self, traces_file: Optional[str] = None):
        self.gp = GenParams(full_core_config)
        self.running = False
        self.cycle_cnt = 0
        self.traces_file = traces_file

        self.log_level = parse_logging_level(os.environ["__TRANSACTRON_LOG_LEVEL"])
        self.log_filter = os.environ["__TRANSACTRON_LOG_FILTER"]

        self.metrics_manager = HardwareMetricsManager()

    def _wishbone_slave(
        self, mem_model: CoreMemoryModel, wb_ctrl: WishboneInterfaceWrapper, is_instr_bus: bool, delay: int = 0
    ):
        def f():
            yield Passive()

            while True:
                yield from wb_ctrl.slave_wait()

                word_width_bytes = self.gp.isa.xlen // 8

                # Wishbone is addressing words, so we need to shift it a bit to get the real address.
                addr = (yield wb_ctrl.wb.adr) << exact_log2(word_width_bytes)
                sel = yield wb_ctrl.wb.sel
                dat_w = yield wb_ctrl.wb.dat_w

                resp_data = 0

                if (yield wb_ctrl.wb.we):
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
                    yield

                yield from wb_ctrl.slave_respond(resp_data, ack=ack, err=err, rty=rty)

                yield Settle()

        return f

    def _waiter(self, on_finish: Callable[[], TestGen[None]]):
        def f():
            while self.running:
                self.cycle_cnt += 1
                yield

            yield from on_finish()

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

    async def run(self, mem_model: CoreMemoryModel, timeout_cycles: int = 5000) -> SimulationExecutionResult:
        with DependencyContext(DependencyManager()):
            core = Core(gen_params=self.gp)

            wb_instr_ctrl = WishboneInterfaceWrapper(core.wb_instr)
            wb_data_ctrl = WishboneInterfaceWrapper(core.wb_data)

            self.running = True
            self.cycle_cnt = 0

            sim = PysimSimulator(core, max_cycles=timeout_cycles, traces_file=self.traces_file)
            sim.add_sync_process(self._wishbone_slave(mem_model, wb_instr_ctrl, is_instr_bus=True))
            sim.add_sync_process(self._wishbone_slave(mem_model, wb_data_ctrl, is_instr_bus=False))

            def on_error():
                raise RuntimeError("Simulation finished due to an error")

            sim.add_sync_process(make_logging_process(self.log_level, self.log_filter, on_error))

            profile = None
            if "__TRANSACTRON_PROFILE" in os.environ:
                transaction_manager = DependencyContext.get().get_dependency(TransactionManagerKey())
                profile = Profile()
                sim.add_sync_process(profiler_process(transaction_manager, profile))

            metric_values: dict[str, dict[str, int]] = {}

            def on_sim_finish():
                # Collect metric values before we finish the simulation
                for metric_name, metric in self.metrics_manager.get_metrics().items():
                    metric = self.metrics_manager.get_metrics()[metric_name]
                    metric_values[metric_name] = {}
                    for reg_name in metric.regs:
                        metric_values[metric_name][reg_name] = yield self.metrics_manager.get_register_value(
                            metric_name, reg_name
                        )

            sim.add_sync_process(self._waiter(on_finish=on_sim_finish))
            success = sim.run()

            self.pretty_dump_metrics(metric_values)

            return SimulationExecutionResult(success, metric_values, profile)

    def stop(self):
        self.running = False
