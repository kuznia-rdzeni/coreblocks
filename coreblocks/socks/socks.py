from amaranth import *
from amaranth.lib.wiring import Component, In, Out, connect, flipped

from coreblocks.arch.isa_consts import InterruptCauseNumber
from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.peripherals.wishbone import WishboneInterface, WishboneMuxer
from coreblocks.priv.traps.interrupt_controller import ISA_RESERVED_INTERRUPTS
from coreblocks.socks.clint import ClintPeriph
from coreblocks.socks.peripheral import bus_in_periph_range

CLINT_BASE = 0xE1000000

# This is a temporary wrapper solution to provide external memory-mapped components, required to run Linux.
# It is intended to be only usable with LiteX, that uses a simple core-facing interface and Wishbone bus
# (and is currenty the only supported integration).
# TODO: Replace this with a proper bus-agnostic (and multicore?) soultion at a later stage.


class Socks(Component):
    wb_instr: WishboneInterface
    wb_data: WishboneInterface
    interrupts: Signal

    def __init__(self, core: Core, core_gen_params: GenParams):
        super().__init__(
            {
                "wb_instr": Out(WishboneInterface(core_gen_params.wb_params).signature),
                "wb_data": Out(WishboneInterface(core_gen_params.wb_params).signature),
                "interrupts": In(ISA_RESERVED_INTERRUPTS + core_gen_params.interrupt_custom_count),
            }
        )

        self.clint = ClintPeriph(base_addr=CLINT_BASE, wb_params=core_gen_params.wb_params)

        self.core = core
        self.core_gen_params = core_gen_params

    def elaborate(self, platform):
        m = Module()

        muxer_ssel = Signal(2)
        periph_muxer = WishboneMuxer(self.core_gen_params.wb_params, 2, muxer_ssel)
        periph_bus = self.clint.bus  # only one peripheral for now

        connect(m, self.core.wb_instr, flipped(self.wb_instr))

        connect(m, self.core.wb_data, periph_muxer.master_wb)
        connect(m, periph_muxer.slaves[0], flipped(self.wb_data))

        connect(m, periph_muxer.slaves[1], periph_bus)

        clint_addr = Signal()
        m.d.comb += clint_addr.eq(bus_in_periph_range(self.core.wb_data, self.clint))
        m.d.comb += muxer_ssel.eq(Cat(~clint_addr, clint_addr))

        m.submodules.clint = self.clint
        m.submodules.periph_muxer = periph_muxer

        m.submodules.core = self.core

        m.d.comb += self.core.interrupts[InterruptCauseNumber.MEI].eq(self.interrupts[InterruptCauseNumber.MEI])
        m.d.comb += self.core.interrupts[InterruptCauseNumber.MTI].eq(self.clint.mtip)
        m.d.comb += self.core.interrupts[InterruptCauseNumber.MSI].eq(self.clint.msip)
        m.d.comb += self.core.interrupts[ISA_RESERVED_INTERRUPTS:].eq(self.interrupts[ISA_RESERVED_INTERRUPTS:])

        return m
