from amaranth import *
from amaranth.lib.wiring import Component, In, Out

from dataclasses import dataclass

from transactron.core.tmodule import SimpleKey
from transactron.lib.dependencies import DependencyContext

from coreblocks.peripherals.wishbone import WishboneInterface, WishboneParameters, WishboneSignature
from coreblocks.soc.common import add_memory_mapped_register


@dataclass(frozen=True)
class ClintMtimeKey(SimpleKey[Value]):
    pass


class ClintPeriph(Component):
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
        space_size: int = 0xC000
    ):
        super().__init__(
            {
                "bus": In(WishboneSignature(wb_params)),
                "mtip": Out(1),
                "msip": Out(hart_count),
            }
        )
        self.time_width = 64
        self.ipi_width = 64
        self.base_addr = base_addr
        self.space_size = space_size
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

        wb_addr_shift = self.bus.dat_r.shape().width // 8
        in_range = (self.bus.adr >= (self.base_addr >> wb_addr_shift)) & (
            self.bus.adr < ((self.base_addr + self.space_size) >> wb_addr_shift)
        )
        with m.If(self.bus.stb & self.bus.cyc & in_range):
            m.d.comb += self.bus.err.eq(1)
            m.d.comb += self.bus.ack.eq(0)

            for hart in range(self.hart_count):
                add_memory_mapped_register(
                    m, self.bus, self.base_addr + self.msip_offset + self.ipi_width * hart, self.ipi[hart]
                )
                add_memory_mapped_register(
                    m, self.bus, self.base_addr + self.mtimecmp_offset + self.time_width * hart, self.mtimecmp[hart]
                )

            add_memory_mapped_register(m, self.bus, self.base_addr + self.mtime_offset, self.mtime)

        return m
