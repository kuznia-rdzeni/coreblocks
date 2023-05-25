from decimal import Decimal
import inspect
from typing import Any
from collections.abc import Coroutine
from dataclasses import dataclass

import cocotb
from cocotb.clock import Clock, Timer
from cocotb.handle import ModifiableObject
from cocotb.triggers import FallingEdge, Event, with_timeout
from cocotb_bus.bus import Bus

from .memory import *
from .common import SimulationBackend


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
                await clock_edge_event

            sig_m = WishboneMasterSignals()
            self.bus.sample(sig_m)

            addr = sig_m.adr << self.word_bits

            sig_s = WishboneSlaveSignals()
            if sig_m.we:
                cocotb.logging.debug(
                    f"Wishbone bus '{self.name}' write request: "
                    f"addr=0x{addr:x} data=0x{int(sig_m.dat_w):x} sel={sig_m.sel}"
                )
                resp = self.model.write(
                    WriteRequest(
                        addr=addr,
                        data=sig_m.dat_w,
                        byte_count=self.word_size,
                        byte_sel=sig_m.sel,
                    )
                )
            else:
                cocotb.logging.debug(f"Wishbone bus '{self.name}' read request: addr=0x{addr:x} sel={sig_m.sel}")
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

            cocotb.logging.debug(
                f"Wishbone bus '{self.name}' response: "
                f"ack={sig_s.ack} err={sig_s.err} rty={sig_s.rty} data={int(sig_s.dat_r):x}"
            )

            for _ in range(self.delay):
                await clock_edge_event

            self.bus.drive(sig_s)
            await clock_edge_event
            self.bus.drive(WishboneSlaveSignals())


class CocotbSimulation(SimulationBackend):
    def __init__(self, dut):
        self.dut = dut
        self.finish_event = Event()

    async def run(self, mem_model: CoreMemoryModel) -> bool:
        clk = Clock(self.dut.clk, 1, "ns")
        cocotb.start_soon(clk.start())

        self.dut.rst.value = 1
        await Timer(Decimal(1), "ns")
        self.dut.rst.value = 0

        instr_wb = WishboneSlave(self.dut, "wb_instr", self.dut.clk, mem_model, is_instr_bus=True)
        cocotb.start_soon(instr_wb.start())

        data_wb = WishboneSlave(self.dut, "wb_data", self.dut.clk, mem_model, is_instr_bus=True)
        cocotb.start_soon(data_wb.start())

        res = await with_timeout(self.finish_event.wait(), 5, "us")

        return res is not None

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
