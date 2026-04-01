from amaranth import *
from coreblocks.params.genparams import GenParams
from coreblocks.interface.layouts import CoreInstructionCounterLayouts
from transactron.core import Method, Provided, TModule, def_method


class CoreInstructionCounter(Elaboratable):
    """
    Counts instructions currently processed in core.
    Used in exception handling, to wait for core flush to finish.
    """

    increment: Provided[Method]
    """Increments the counter. Should be called when new instruction leaves fetch stage."""

    decrement: Provided[Method]
    """Decrements the counter. Should be called when instruction is retired.
    Returns a boolean saying if the counter will be equal to zero after that cycle (it was the
    last instruction in core and no new instruction is fetched).
    """

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = gen_params.get(CoreInstructionCounterLayouts)
        self.increment = Method(i=layouts.increment_in)
        self.decrement = Method(i=layouts.decrement_in, o=layouts.decrement_out)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        counter = Signal(self.gen_params.rob_entries_bits + 1)
        counter_next = Signal.like(counter)
        incr_value = Signal(self.increment.layout_in.members["count"])
        decr_value = Signal(self.decrement.layout_in.members["count"])

        m.d.comb += counter_next.eq(counter + incr_value - decr_value)
        m.d.sync += counter.eq(counter_next)

        limit = (2 ** counter.shape().width) - self.gen_params.frontend_superscalarity

        @def_method(m, self.increment, ready=counter < limit)
        def _(count):
            m.d.comb += incr_value.eq(count)

        @def_method(m, self.decrement)
        def _(count):
            m.d.comb += decr_value.eq(count)
            return counter_next == 0

        return m
