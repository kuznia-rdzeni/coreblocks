from collections.abc import Callable, Coroutine
from typing import Any, TypeAlias
import cocotb
from cocotb.regression import TestFactory
from cocotb.handle import ModifiableObject
from cocotb.triggers import RisingEdge
from cocotb_bus.bus import Bus
from dataclasses import dataclass


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
        super().__init__(entity, name, self._signals, self._optional_signals, bus_separator="__")


WishboneHandler: TypeAlias = Callable[[WishboneMasterSignals], Coroutine[Any, Any, WishboneSlaveSignals]]


class WishboneSlave:
    def __init__(self, entity, name, clock, handler: WishboneHandler):
        self.entity = entity
        self.name = name
        self.clock = clock
        self.handler = handler
        self.bus = WishboneBus(entity, name)

    async def _run(self):
        clock_edge_event = RisingEdge(self.clock)

        while True:
            while not (self.bus.stb.value and self.bus.cyc.value):
                await clock_edge_event

            sig_m = WishboneMasterSignals()
            self.bus.sample(sig_m)

            sig_s = WishboneSlaveSignals()
            while not (sig_s.ack or sig_s.err or sig_s.rty):
                await self.handler(sig_m)
            
            if sig_s.rty and not self.bus.rty:
                raise ValueError("Bus doesn't support rty")
            if sig_s.err and not self.bus.err:
                raise ValueError("Bus doesn't support err")

            self.bus.drive(sig_s)


class MemoryModel:
    def __init__(self, clock, delay=1):
        self.clock = clock
        self.delay = delay

    async def handler(self, sig: WishboneMasterSignals) -> WishboneSlaveSignals:
        pass


async def test(dut, test_name):
    instr_mem = MemoryModel(dut.clk)

    wb_instr = WishboneSlave(
        dut,
        "wb_instr",
        dut.clk,
        instr_mem.handler
    )

    data_mem = MemoryModel(dut.clk)

    wb_data = WishboneSlave(
        dut,
        "wb_data",
        dut.clk,
        data_mem.handler
    )

tf = TestFactory(test)
tf.add_option('test_name', ['add', 'addi'])
tf.generate_tests()

