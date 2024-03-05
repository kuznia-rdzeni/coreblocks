import re

from amaranth.sim import Passive, Settle
from amaranth.utils import exact_log2
from amaranth import *

from .memory import *
from .common import SimulationBackend, SimulationExecutionResult

from transactron.testing import PysimSimulator, TestGen
from transactron.utils.dependencies import DependencyContext, DependencyManager
from transactron.lib.metrics import HardwareMetricsManager
from ..peripherals.test_wishbone import WishboneInterfaceWrapper

from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.params.configurations import full_core_config
from coreblocks.peripherals.wishbone import WishboneBus


class PySimulation(SimulationBackend):
    def __init__(self, verbose: bool, traces_file: Optional[str] = None):
        self.gp = GenParams(full_core_config)
        self.running = False
        self.cycle_cnt = 0
        self.verbose = verbose
        self.traces_file = traces_file

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

                bus_name = "instr" if is_instr_bus else "data"

                if (yield wb_ctrl.wb.we):
                    if self.verbose:
                        print(f"Wishbone '{bus_name}' bus write request: addr=0x{addr:x} data={dat_w:x} sel={sel:b}")
                    resp = mem_model.write(
                        WriteRequest(addr=addr, data=dat_w, byte_count=word_width_bytes, byte_sel=sel)
                    )
                else:
                    if self.verbose:
                        print(f"Wishbone '{bus_name}' bus read request: addr=0x{addr:x} sel={sel:b}")
                    resp = mem_model.read(
                        ReadRequest(
                            addr=addr,
                            byte_count=word_width_bytes,
                            byte_sel=sel,
                            exec=is_instr_bus,
                        )
                    )
                    resp_data = resp.data

                    if self.verbose:
                        print(f"Wishbone '{bus_name}' bus read response: data=0x{resp.data:x}")

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
        print()
        print("=== Core metrics dump ===")

        put_space_before = True
        for metric_name in sorted(metric_values.keys()):
            if not re.search(filter_regexp, metric_name):
                continue

            metric = self.metrics_manager.get_metrics()[metric_name]

            if metric.description != "":
                if not put_space_before:
                    print()

                print(f"# {metric.description}")

            for reg in metric.regs.values():
                reg_value = metric_values[metric_name][reg.name]

                desc = f" # {reg.description} [reg width={reg.width}]"
                print(f"{metric_name}/{reg.name} {reg_value}{desc}")

            put_space_before = False
            if metric.description != "":
                print()
                put_space_before = True

    async def run(self, mem_model: CoreMemoryModel, timeout_cycles: int = 5000) -> SimulationExecutionResult:
        with DependencyContext(DependencyManager()):
            wb_instr_bus = WishboneBus(self.gp.wb_params)
            wb_data_bus = WishboneBus(self.gp.wb_params)
            core = Core(gen_params=self.gp, wb_instr_bus=wb_instr_bus, wb_data_bus=wb_data_bus)

            wb_instr_ctrl = WishboneInterfaceWrapper(wb_instr_bus)
            wb_data_ctrl = WishboneInterfaceWrapper(wb_data_bus)

            self.running = True
            self.cycle_cnt = 0

            sim = PysimSimulator(core, max_cycles=timeout_cycles, traces_file=self.traces_file)
            sim.add_sync_process(self._wishbone_slave(mem_model, wb_instr_ctrl, is_instr_bus=True))
            sim.add_sync_process(self._wishbone_slave(mem_model, wb_data_ctrl, is_instr_bus=False))

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

            if self.verbose:
                self.pretty_dump_metrics(metric_values)

            return SimulationExecutionResult(success, metric_values)

    def stop(self):
        self.running = False
