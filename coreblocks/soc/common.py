from amaranth import *
from amaranth_types import ModuleLike

from coreblocks.peripherals.wishbone import WishboneInterface


def add_memory_mapped_register(m: ModuleLike, bus: WishboneInterface, byte_addr: int, register: Signal):
    reg_width = register.shape().width
    word_width = bus.dat_r.shape().width
    addr_shift = (word_width // 8) - 1
    words_in_reg = (reg_width + word_width - 1) // word_width
    wishbone_addr = byte_addr >> addr_shift
    assert wishbone_addr << addr_shift == byte_addr
    granularity_bits = word_width // max(1, bus.sel.shape().width)

    with m.If(bus.stb & bus.cyc):
        for word in range(words_in_reg):
            reg_slice = register[word * word_width : min(reg_width, (word + 1) * word_width)]
            with m.If(bus.adr == wishbone_addr + word):
                m.d.comb += bus.dat_r.eq(reg_slice)
                m.d.comb += bus.ack.eq(1)
                m.d.comb += bus.err.eq(0)
                with m.If(bus.we):
                    granularity_mask = 0 if bus.sel.shape().width > 0 else ((1 << word_width) - 1)
                    for i in range(bus.sel.shape().width):
                        granularity_mask |= bus.sel[i].replicate(granularity_bits) << (i * granularity_bits)

                    m.d.sync += reg_slice.eq((bus.dat_w & granularity_mask) | (reg_slice & ~granularity_mask))
