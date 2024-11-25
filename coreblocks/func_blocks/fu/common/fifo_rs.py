from amaranth import *
from transactron import TModule
from coreblocks.func_blocks.fu.common.rs import RSBase

__all__ = ["FifoRS"]


class FifoRS(RSBase):
    def elaborate(self, platform):
        m = TModule()

        front = Signal(self.rs_entries_bits)
        back = Signal(self.rs_entries_bits)

        select_possible = ~self.flags[back].rec_reserved

        take_possible = self.data_ready.bit_select(front, 1) & self.flags[front].rec_full
        take_vector = take_possible << front

        self._elaborate(m, back, select_possible, take_vector)

        with m.If(self.select.run):
            m.d.sync += back.eq(back + 1)

        with m.If(self.take.run):
            m.d.sync += front.eq(front + 1)

        return m
