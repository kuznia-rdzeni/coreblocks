from amaranth import *
from amaranth.lib.wiring import Component, In, Out, connect, flipped

from coreblocks.arch.isa_consts import InterruptCauseNumber
from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.peripherals.wishbone import WishboneInterface, WishboneMuxer, WishboneSignature
from coreblocks.priv.traps.interrupt_controller import ISA_RESERVED_INTERRUPTS
from coreblocks.soc.clint import ClintPeriph


class SoC(Component):
    wb_instr: WishboneInterface
    wb_data: WishboneInterface
    interrupts: Signal

    def __init__(self, core: Core, core_gen_params: GenParams):
        super().__init__(
            {
                "wb_instr": Out(WishboneSignature(core_gen_params.wb_params)),
                "wb_data": Out(WishboneSignature(core_gen_params.wb_params)),
                "interrupts": In(ISA_RESERVED_INTERRUPTS + core_gen_params.interrupt_custom_count),
            }
        )

        self.clint = ClintPeriph(base_addr=0xE1000000, wb_params=core_gen_params.wb_params)

        self.core = core
        self.core_gen_params = core_gen_params

    def elaborate(self, platform):
        m = Module()

        muxer_ssel = Signal(2)
        periph_muxer = WishboneMuxer(self.core_gen_params.wb_params, 2, muxer_ssel)

        connect(m, self.core.wb_instr, flipped(self.wb_instr))

        connect(m, self.core.wb_data, periph_muxer.master_wb)
        connect(m, periph_muxer.slaves[0], flipped(self.wb_data))

        connect(m, periph_muxer.slaves[1], self.clint.bus)

        in_core_periph_space = Signal()
        m.d.comb += in_core_periph_space.eq(
            (self.core.wb_data.adr <= self.clint.base_addr)
            & (self.core.wb_data.adr > self.clint.base_addr + self.clint.space_size)
        )
        m.d.comb += muxer_ssel.eq(Cat(~in_core_periph_space, in_core_periph_space))

        m.submodules.clint = self.clint
        m.submodules.periph_muxer = periph_muxer

        m.submodules.core = self.core

        m.d.comb += self.core.interrupts[InterruptCauseNumber.MEI].eq(self.clint.mtip)
        m.d.comb += self.core.interrupts[InterruptCauseNumber.MSI].eq(self.clint.msip)
        m.d.comb += self.core.interrupts[ISA_RESERVED_INTERRUPTS:].eq(self.interrupts[ISA_RESERVED_INTERRUPTS:])

        return m
