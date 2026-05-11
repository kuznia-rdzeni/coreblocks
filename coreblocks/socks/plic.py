from amaranth import *
from amaranth.lib.data import StructLayout
from amaranth.lib.wiring import Component, In, Out

from transactron.utils import assign

from coreblocks.peripherals.wishbone import WishboneInterface, WishboneParameters
from coreblocks.socks.peripheral import (
    SocksPeripheral,
    convert_to_wishbone_addr,
    gen_memory_mapped_register,
    is_perpiheral_request,
)

MIN_PRIORITY = 1
PRIORITY_COUNT = 7

MAX_INTERRUPTS = 1024
MAX_CONTEXTS = 15872

OFFSET_SOURCE_PRIORITY = 0x000000
OFFSET_PENDING_BIT = 0x001000
OFFSET_ENABLE_BIT = 0x002000

OFFSET_CONTEXT_REGS = 0x200000
CONTEXT_REGS_SIZE = 0x000008
OFFSET_CONTEXT_PRIORITY_TRESHOLD = 0x0
OFFSET_CONTEXT_INTERRUPT_CLAIM = 0x4


class PlicPeriph(Component, SocksPeripheral):
    bus: WishboneInterface
    interrupts: Signal
    eip: Signal

    def __init__(
        self,
        base_addr: int,
        *,
        wb_params: WishboneParameters,
        context_count: int = 1,
        priority_bits: int = 3,
        interrupt_count: int = 16,
        addr_space_size: int = 0x4000000,
    ):
        super().__init__(
            {
                "bus": In(WishboneInterface(wb_params).signature),
                "interrupts": In(interrupt_count),
                "eip": Out(context_count),
            }
        )
        self.interrupt_count = interrupt_count
        self.context_count = context_count
        self.priority_bits = priority_bits

        self.base_addr = base_addr
        self.addr_space_size = addr_space_size

    def elaborate(self, platform):
        m = Module()

        pending = Signal(self.interrupt_count)
        pending_to_disable = Signal.like(pending)
        processing = Signal(self.interrupt_count)
        processing_to_disable = Signal.like(processing)
        enable = Array([Signal(self.interrupt_count)] * self.context_count)
        context_treshold = Array([Signal(self.priority_bits)] * self.context_count)
        interrupt_priority = Array([Signal(self.priority_bits)] * self.interrupt_count)

        # Step 1: Mask currently processed interrupts

        # interrupt 0 is reserved and hard-wired to 0
        pending_to_enable = self.interrupts & ~processing & ~(1 << 0)
        m.d.sync += pending.eq((pending & ~pending_to_disable) | (pending_to_enable & ~C(1)))
        m.d.sync += processing.eq((processing & ~processing_to_disable) | pending_to_enable)

        # Step 2: Set context EIPs if conditions match

        pending_per_priority = Array([Signal(self.interrupt_count) * PRIORITY_COUNT])
        for priority in range(MIN_PRIORITY, PRIORITY_COUNT):
            per_interrupt = [
                pending[interrupt] & (interrupt_priority[interrupt] == priority)
                for interrupt in range(self.interrupt_count)
            ]
            m.d.comb += pending_per_priority[priority].eq(Cat(per_interrupt))

        eip_comb = []
        per_context_selected_priority_pendings = Array([Signal(self.interrupt_count)] * self.context_count)
        for context in range(self.context_count):
            priority_sel = Signal(self.priority_bits)
            for priority in range(MIN_PRIORITY, PRIORITY_COUNT):
                with m.If((pending_per_priority[priority] & enable[context]).any()):
                    m.d.comb += priority_sel.eq(priority)
            eip_comb.append(priority_sel > context_treshold[context])
            m.d.sync += per_context_selected_priority_pendings[context].eq(pending_per_priority[priority_sel])
        m.d.sync += self.eip.eq(Cat(eip_comb))

        # Step 3. Service claim/completion requests

        claim_complete_for_context = Signal(
            StructLayout(
                {
                    "context": range(self.context_count),
                    "claim": 1,
                    "complete": 1,
                    "complete_interrupt": range(self.interrupt_count),
                }
            )
        )
        claim_resonse = Signal(StructLayout({"value": self.bus.dat_r.shape(), "set": 1}))

        for context in range(self.context_count):
            claim_addr = convert_to_wishbone_addr(
                self.bus,
                self.base_addr + OFFSET_CONTEXT_REGS + context * CONTEXT_REGS_SIZE + OFFSET_CONTEXT_INTERRUPT_CLAIM,
            )
            with m.If(is_perpiheral_request(self) & (self.bus.adr == claim_addr)):
                m.d.comb += assign(
                    claim_complete_for_context,
                    {
                        "context": context,
                        "claim": ~self.bus.we,
                        "complete": self.bus.we,
                        "complete_interrupt": self.bus.dat_w,
                    },
                )

        with m.If(claim_complete_for_context.claim):
            claimed_interrupt = Signal(range(self.interrupt_count))
            for interrupt in range(self.interrupt_count):
                with m.If(per_context_selected_priority_pendings[claim_complete_for_context.context]):
                    m.d.comb += claimed_interrupt.eq(interrupt)

                m.d.sync += assign(claim_resonse, {"value": claimed_interrupt, "set": 1})
                with m.If(claimed_interrupt.any()):
                    m.d.comb += pending_to_disable.bit_select(claimed_interrupt, 1).eq(1)
                m.d.comb += self.bus.ack.eq(0)
                m.d.comb += self.bus.err.eq(0)

        # write registered value from previous cycle (cut comb paths on bus)
        with m.If(claim_resonse.set):
            m.d.comb += self.bus.dat_r.eq(claim_resonse.value)
            m.d.comb += self.bus.ack.eq(1)
            m.d.comb += self.bus.err.eq(0)
            m.d.sync += claim_resonse.set.eq(0)

        with m.If(claim_complete_for_context.complete):
            m.d.comb += processing_to_disable.bit_select(claim_complete_for_context, 1).eq(1)
            m.d.comb += self.bus.ack.eq(1)
            m.d.comb += self.bus.err.eq(0)

        with m.If(is_perpiheral_request(self)):
            m.d.comb += self.bus.err.eq(1)  # default - overwritten by memory mapped registers declaration
            m.d.comb += self.bus.ack.eq(0)

        for interrupt in range(self.interrupt_count):
            gen_memory_mapped_register(
                m, self, self.base_addr + OFFSET_SOURCE_PRIORITY + 4 * interrupt, interrupt_priority[interrupt]
            )
        gen_memory_mapped_register(m, self, self.base_addr + OFFSET_PENDING_BIT, pending, read_only=True)

        for context in range(self.context_count):
            gen_memory_mapped_register(
                m, self, self.base_addr + OFFSET_ENABLE_BIT + context * (MAX_INTERRUPTS // 8), enable[context]
            )
            gen_memory_mapped_register(
                m,
                self,
                self.base_addr + OFFSET_CONTEXT_REGS + context * CONTEXT_REGS_SIZE + OFFSET_CONTEXT_PRIORITY_TRESHOLD,
                context_treshold[context],
            )

        return m
