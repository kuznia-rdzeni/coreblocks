from amaranth import *
from amaranth.lib.wiring import Component, In, Out

from dataclasses import dataclass

from transactron.core.tmodule import SimpleKey
from transactron.lib.dependencies import DependencyContext

from coreblocks.peripherals.wishbone import WishboneInterface, WishboneParameters
from coreblocks.socks.peripheral import SocksPeripheral, gen_memory_mapped_register, is_perpiheral_request


@dataclass(frozen=True)
class ClintMtimeKey(SimpleKey[Value]):
    pass


class ClintPeriph(Component, SocksPeripheral):
    bus: WishboneInterface
    mtip: Signal
    msip: Signal

    def __init__(
        self,
        base_addr: int,
        *,
        wb_params: WishboneParameters,
        hart_count: int = 1,
        msip_offset=0x0000,
        mtimecmp_offset=0x4000,
        mtime_offset=0xBFF8,
        addr_space_size: int = 0xC000
    ):
        super().__init__(
            {
                "bus": In(WishboneInterface(wb_params).signature),
                "mtip": Out(1),
                "msip": Out(hart_count),
            }
        )
        self.time_width = 64
        self.ipi_width = 64
        self.base_addr = base_addr
        self.addr_space_size = addr_space_size
        self.hart_count = hart_count

        self.msip_offset = msip_offset
        self.mtimecmp_offset = mtimecmp_offset
        self.mtime_offset = mtime_offset

        self.mtime = Signal(self.time_width)
        self.mtimecmp = [Signal(self.time_width) for _ in range(self.hart_count)]
        self.ipi = [Signal() for _ in range(self.hart_count)]

        dm = DependencyContext.get()
        dm.add_dependency(ClintMtimeKey(), self.mtime)

    def elaborate(self, platform):
        m = Module()

        m.d.sync += self.mtime.eq(self.mtime + 1)

        for i in range(self.hart_count):
            m.d.comb += self.mtip[i].eq(self.mtime >= self.mtimecmp[i])
            m.d.comb += self.msip[i].eq(self.ipi[i])

        with m.If(is_perpiheral_request(self)):
            m.d.comb += self.bus.err.eq(1)  # default - overwritten by memory mapped registers declaration
            m.d.comb += self.bus.ack.eq(0)

        for hart in range(self.hart_count):
            gen_memory_mapped_register(m, self, self.msip_offset + self.ipi_width * hart, self.ipi[hart])
            gen_memory_mapped_register(m, self, self.mtimecmp_offset + self.time_width * hart, self.mtimecmp[hart])

        gen_memory_mapped_register(m, self, self.mtime_offset, self.mtime)

        return m
