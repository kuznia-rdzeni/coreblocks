from amaranth import *

from transactron import *
from transactron.utils.transactron_helpers import make_layout

from coreblocks.params import GenParams, RASConfig

__all__ = ["RAS"]


class RAS(Elaboratable):
    """A simple return address stack.

    It is only a best-effort prediction, so overflow and underflow are allowed. Wrong-path
    speculation can also corrupt the stack, as a checkpoint only recovers the top entry.
    """

    peek: Provided[Method]
    """Return the address on top of the stack, if there is one."""

    update: Provided[Method]
    """Push and/or pop a return address. Returns the new state, to be saved in a checkpoint."""

    recover: Provided[Method]
    """Restore a state previously returned by `update`."""

    def __init__(self, gen_params: GenParams, config: RASConfig):
        self.gen_params = gen_params

        self.depth = 2**config.entries_log
        xlen = gen_params.isa.xlen

        self.state_layout = make_layout(
            ("sp", range(self.depth)),
            ("count", range(self.depth + 1)),
            ("top", xlen),
        )
        self.peek_layout = make_layout(("valid", 1), ("addr", xlen))
        self.update_layout = make_layout(("push", 1), ("pop", 1), ("addr", xlen))

        self.peek = Method(o=self.peek_layout)
        self.update = Method(i=self.update_layout, o=self.state_layout)
        self.recover = Method(i=self.state_layout)

    def elaborate(self, platform):
        m = TModule()

        xlen = self.gen_params.isa.xlen

        stack = Array(Signal(xlen, name=f"ras_entry_{i}") for i in range(self.depth))
        sp_reg = Signal(range(self.depth))
        count_reg = Signal(range(self.depth + 1))

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            return {"valid": count_reg != 0, "addr": stack[sp_reg]}

        @def_method(m, self.update)
        def _(push, pop, addr):
            sp_inc = Signal(range(self.depth))
            sp_dec = Signal(range(self.depth))
            m.d.av_comb += sp_inc.eq(sp_reg + 1)
            m.d.av_comb += sp_dec.eq(sp_reg - 1)

            new_sp = Signal.like(sp_reg)
            new_count = Signal.like(count_reg)
            new_top = Signal(xlen)
            m.d.av_comb += [new_sp.eq(sp_reg), new_count.eq(count_reg), new_top.eq(stack[sp_reg])]

            with m.If(push & pop):
                m.d.av_comb += new_top.eq(addr)
                m.d.sync += stack[sp_reg].eq(addr)
            with m.Elif(push):
                m.d.av_comb += new_sp.eq(sp_inc)
                m.d.av_comb += new_count.eq(Mux(count_reg == self.depth, self.depth, count_reg + 1))
                m.d.av_comb += new_top.eq(addr)
                m.d.sync += stack[sp_inc].eq(addr)
            with m.Elif(pop):
                m.d.av_comb += new_sp.eq(sp_dec)
                m.d.av_comb += new_count.eq(Mux(count_reg == 0, 0, count_reg - 1))
                m.d.av_comb += new_top.eq(stack[sp_dec])

            m.d.sync += sp_reg.eq(new_sp)
            m.d.sync += count_reg.eq(new_count)

            return {"sp": new_sp, "count": new_count, "top": new_top}

        @def_method(m, self.recover)
        def _(sp, count, top):
            m.d.sync += sp_reg.eq(sp)
            m.d.sync += count_reg.eq(count)
            m.d.sync += stack[sp].eq(top)

        return m
