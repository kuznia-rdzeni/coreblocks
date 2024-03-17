from decimal import Decimal
import inspect
import re
import os
from typing import Any
from collections.abc import Coroutine
from dataclasses import dataclass

import cocotb
from cocotb.clock import Clock, Timer
from cocotb.handle import ModifiableObject
from cocotb.triggers import FallingEdge, Event, RisingEdge, with_timeout
from cocotb_bus.bus import Bus
from cocotb.result import SimTimeoutError

from .memory import *
from .common import SimulationBackend, SimulationExecutionResult

from transactron.profiler import CycleProfile, MethodSamples, Profile, ProfileSamples, TransactionSamples
from transactron.utils.gen import GenerationInfo


@dataclass
class WishboneMasterSignals:
    adr: Any = 0
    we: Any = 0
    sel: Any = 0
    dat_w: Any = 0


@dataclass
class WishboneSlaveSignals:
    dat_r: Any = 0
    ack: Any = 0
    err: Any = 0
    rty: Any = 0


class WishboneBus(Bus):
    _signals = ["cyc", "stb", "we", "adr", "dat_r", "dat_w", "ack"]
    _optional_signals = ["sel", "err", "rty"]

    cyc: ModifiableObject
    stb: ModifiableObject
    we: ModifiableObject
    adr: ModifiableObject
    dat_r: ModifiableObject
    dat_w: ModifiableObject
    ack: ModifiableObject
    sel: ModifiableObject
    err: ModifiableObject
    rty: ModifiableObject

    def __init__(self, entity, name):
        # case_insensitive is a workaround for cocotb_bus/verilator problem
        # see https://github.com/cocotb/cocotb/issues/3259
        super().__init__(
            entity, name, self._signals, self._optional_signals, bus_separator="__", case_insensitive=False
        )


class WishboneSlave:
    def __init__(
        self, entity, name: str, clock, model: CoreMemoryModel, is_instr_bus: bool, word_bits: int = 2, delay: int = 0
    ):
        self.entity = entity
        self.name = name
        self.clock = clock
        self.model = model
        self.is_instr_bus = is_instr_bus
        self.word_size = 2**word_bits
        self.word_bits = word_bits
        self.delay = delay
        self.bus = WishboneBus(entity, name)
        self.bus.drive(WishboneSlaveSignals())

    async def start(self):
        clock_edge_event = FallingEdge(self.clock)

        while True:
            while not (self.bus.stb.value and self.bus.cyc.value):
                await clock_edge_event  # type: ignore

            sig_m = WishboneMasterSignals()
            self.bus.sample(sig_m)

            addr = sig_m.adr << self.word_bits

            sig_s = WishboneSlaveSignals()
            if sig_m.we:
                resp = self.model.write(
                    WriteRequest(
                        addr=addr,
                        data=sig_m.dat_w,
                        byte_count=self.word_size,
                        byte_sel=sig_m.sel,
                    )
                )
            else:
                resp = self.model.read(
                    ReadRequest(
                        addr=addr,
                        byte_count=self.word_size,
                        byte_sel=sig_m.sel,
                        exec=self.is_instr_bus,
                    )
                )
                sig_s.dat_r = resp.data

            match resp.status:
                case ReplyStatus.OK:
                    sig_s.ack = 1
                case ReplyStatus.ERROR:
                    if not self.bus.err:
                        raise ValueError("Bus doesn't support err")
                    sig_s.err = 1
                case ReplyStatus.RETRY:
                    if not self.bus.rty:
                        raise ValueError("Bus doesn't support rty")
                    sig_s.rty = 1

            for _ in range(self.delay):
                await clock_edge_event  # type: ignore

            self.bus.drive(sig_s)
            await clock_edge_event  # type: ignore
            self.bus.drive(WishboneSlaveSignals())


class CocotbSimulation(SimulationBackend):
    def __init__(self, dut):
        self.dut = dut
        self.finish_event = Event()

        try:
            gen_info_path = os.environ["_COREBLOCKS_GEN_INFO"]
        except KeyError:
            raise RuntimeError("No core generation info provided")

        self.gen_info = GenerationInfo.decode(gen_info_path)

        self.log_level = os.environ["__TRANSACTRON_LOG_LEVEL"]
        self.log_filter = os.environ["__TRANSACTRON_LOG_FILTER"]

        cocotb.logging.getLogger().setLevel(self.log_level)

    def get_cocotb_handle(self, path_components: list[str]) -> ModifiableObject:
        obj = self.dut
        # Skip the first component, as it is already referenced in "self.dut"
        for component in path_components[1:]:
            try:
                # As the component may start with '_' character, we need to use '_id'
                # function instead of 'getattr' - this is required by cocotb.
                obj = obj._id(component, extended=False)
            except AttributeError:
                # Try with escaped name
                if component[0] != "\\" and component[-1] != " ":
                    obj = obj._id("\\" + component + " ", extended=False)
                else:
                    raise

        return obj

    async def profile_handler(self, clock, profile: Profile):
        clock_edge_event = RisingEdge(clock)

        while True:
            samples = ProfileSamples()

            for transaction_id, location in self.gen_info.transaction_signals_location.items():
                request_val = self.get_cocotb_handle(location.request)
                runnable_val = self.get_cocotb_handle(location.runnable)
                grant_val = self.get_cocotb_handle(location.grant)
                samples.transactions[transaction_id] = TransactionSamples(
                    bool(request_val.value), bool(runnable_val.value), bool(grant_val.value)
                )

            for method_id, location in self.gen_info.method_signals_location.items():
                run_val = self.get_cocotb_handle(location.run)
                samples.methods[method_id] = MethodSamples(bool(run_val.value))

            cprof = CycleProfile.make(samples, self.gen_info.profile_data)
            profile.cycles.append(cprof)

            await clock_edge_event  # type: ignore

    async def logging_handler(self, clock):
        clock_edge_event = FallingEdge(clock)

        log_level = cocotb.logging.getLogger().level

        logs = [
            (rec, self.get_cocotb_handle(rec.trigger_location))
            for rec in self.gen_info.logs
            if rec.level >= log_level and re.search(self.log_filter, rec.logger_name)
        ]

        while True:
            for rec, trigger_handle in logs:
                if not trigger_handle.value:
                    continue

                values: list[int] = []
                for field in rec.fields_location:
                    values.append(int(self.get_cocotb_handle(field).value))

                formatted_msg = rec.format(*values)

                cocotb_log = cocotb.logging.getLogger(rec.logger_name)

                cocotb_log.log(
                    rec.level,
                    "%s:%d] %s",
                    rec.location[0],
                    rec.location[1],
                    formatted_msg,
                )

                if rec.level >= cocotb.logging.ERROR:
                    assert False, f"Assertion failed at {rec.location[0], rec.location[1]}: {formatted_msg}"

            await clock_edge_event  # type: ignore

    async def run(self, mem_model: CoreMemoryModel, timeout_cycles: int = 5000) -> SimulationExecutionResult:
        clk = Clock(self.dut.clk, 1, "ns")
        cocotb.start_soon(clk.start())

        self.dut.rst.value = 1
        await Timer(Decimal(1), "ns")
        self.dut.rst.value = 0

        instr_wb = WishboneSlave(self.dut, "wb_instr", self.dut.clk, mem_model, is_instr_bus=True)
        cocotb.start_soon(instr_wb.start())

        data_wb = WishboneSlave(self.dut, "wb_data", self.dut.clk, mem_model, is_instr_bus=False)
        cocotb.start_soon(data_wb.start())

        profile = None
        if "__TRANSACTRON_PROFILE" in os.environ:
            profile = Profile()
            profile.transactions_and_methods = self.gen_info.profile_data.transactions_and_methods
            cocotb.start_soon(self.profile_handler(self.dut.clk, profile))

        cocotb.start_soon(self.logging_handler(self.dut.clk))

        success = True
        try:
            await with_timeout(self.finish_event.wait(), timeout_cycles, "ns")
        except SimTimeoutError:
            success = False

        result = SimulationExecutionResult(success)

        result.profile = profile

        for metric_name, metric_loc in self.gen_info.metrics_location.items():
            result.metric_values[metric_name] = {}
            for reg_name, reg_loc in metric_loc.regs.items():
                value = int(self.get_cocotb_handle(reg_loc))
                result.metric_values[metric_name][reg_name] = value
                cocotb.logging.info(f"Metric {metric_name}/{reg_name}={value}")

        return result

    def stop(self):
        self.finish_event.set()


def _create_test(function, name, mod, *args, **kwargs):
    async def _my_test(dut):
        await function(dut, *args, **kwargs)

    _my_test.__name__ = name
    _my_test.__qualname__ = name
    _my_test.__module__ = mod.__name__

    return cocotb.test()(_my_test)


def generate_tests(test_function: Callable[[Any, Any], Coroutine[Any, Any, None]], test_names: list[str]):
    frm = inspect.stack()[1]
    mod = inspect.getmodule(frm[0])

    for test_name in test_names:
        setattr(mod, test_name, _create_test(test_function, test_name, mod, test_name))
