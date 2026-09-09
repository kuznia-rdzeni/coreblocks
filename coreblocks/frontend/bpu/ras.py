from amaranth import *
from amaranth.lib import memory

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

        m.submodules.mem = mem = memory.Memory(shape=xlen, depth=self.depth, init=[])
        write_port = mem.write_port()
        read_port = mem.read_port()

        sp_reg = Signal(range(self.depth))
        count_reg = Signal(range(self.depth + 1))
        top_reg = Signal(xlen)

        sp_inc = Signal(range(self.depth))
        sp_dec = Signal(range(self.depth))
        m.d.comb += [sp_inc.eq(sp_reg + 1), sp_dec.eq(sp_reg - 1)]

        next_sp = Signal(range(self.depth))
        m.d.comb += next_sp.eq(sp_reg)

        m.d.comb += read_port.addr.eq(next_sp - 1)

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            return {"valid": count_reg != 0, "addr": top_reg}

        @def_method(m, self.update)
        def _(push, pop, addr):
            new_sp = Signal.like(sp_reg)
            new_count = Signal.like(count_reg)
            new_top = Signal(xlen)
            m.d.av_comb += [new_sp.eq(sp_reg), new_count.eq(count_reg), new_top.eq(top_reg)]

            with m.If(push & pop):
                m.d.av_comb += new_top.eq(addr)
                m.d.comb += [write_port.en.eq(1), write_port.addr.eq(sp_reg), write_port.data.eq(addr)]
            with m.Elif(push):
                m.d.av_comb += new_sp.eq(sp_inc)
                m.d.av_comb += new_count.eq(Mux(count_reg == self.depth, self.depth, count_reg + 1))
                m.d.av_comb += new_top.eq(addr)
                m.d.comb += [write_port.en.eq(1), write_port.addr.eq(sp_inc), write_port.data.eq(addr)]
            with m.Elif(pop):
                m.d.av_comb += new_sp.eq(sp_dec)
                m.d.av_comb += new_count.eq(Mux(count_reg == 0, 0, count_reg - 1))
                m.d.av_comb += new_top.eq(read_port.data)

            m.d.comb += next_sp.eq(new_sp)
            m.d.sync += sp_reg.eq(new_sp)
            m.d.sync += count_reg.eq(new_count)
            m.d.sync += top_reg.eq(new_top)

            return {"sp": new_sp, "count": new_count, "top": new_top}

        @def_method(m, self.recover)
        def _(sp, count, top):
            m.d.comb += next_sp.eq(sp)
            m.d.sync += sp_reg.eq(sp)
            m.d.sync += count_reg.eq(count)
            m.d.sync += top_reg.eq(top)
            m.d.comb += [write_port.en.eq(1), write_port.addr.eq(sp), write_port.data.eq(top)]

        return m
