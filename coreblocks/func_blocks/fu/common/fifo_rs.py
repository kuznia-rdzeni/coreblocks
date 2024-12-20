from amaranth import *
from amaranth.lib.data import ArrayLayout
from transactron import Method, TModule, def_method
from transactron.utils import mod_incr
from coreblocks.func_blocks.fu.common.rs import RSBase

__all__ = ["FifoRS"]


class FifoRS(RSBase):
    def elaborate(self, platform):
        m = TModule()

        alloc = Method(o=[("ident", range(self.rs_entries))])
        free_idx = Method(i=[("idx", range(self.rs_entries))])
        order = Method(o=[("order", ArrayLayout(range(self.rs_entries), self.rs_entries))], nonexclusive=True)

        front = Signal(range(self.rs_entries))
        back = Signal(range(self.rs_entries))
        reserved = Signal(self.rs_entries)

        @def_method(m, order)
        def _():
            return {"order": [front for _ in range(self.rs_entries)]}

        @def_method(m, alloc, ~reserved.all())
        def _():
            m.d.sync += reserved.bit_select(back, 1).eq(1)
            m.d.sync += back.eq(mod_incr(back, self.rs_entries))
            return {"ident": back}

        @def_method(m, free_idx)
        def _(idx):
            m.d.sync += reserved.bit_select(front, 1).eq(0)
            m.d.sync += front.eq(mod_incr(front, self.rs_entries))

        self._elaborate(m, alloc, free_idx, order)

        return m
