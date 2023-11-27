from amaranth import *
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import CoreInstructionCounterLayouts
from transactron.core import Method, TModule, def_method


class CoreInstructionCounter(Elaboratable):
    """
    Counts instructions currently processed in core.
    Used in exception handling, to wait for core flush to finish.

    Attributes
    ----------
    increment : Method
        Increments the counter. Should be called when new instruction leaves fetch stage.
    decrement : Method
        Decrements the counter, and returns if the counter will be equal to zero after that cycle (it was the
        last instruction in core and no new instruction is fetched). Should be called when instruction is retired.
    """

    def __init__(self, gp: GenParams):
        self.gp = gp

        self.increment = Method()
        self.decrement = Method(o=gp.get(CoreInstructionCounterLayouts).decrement)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        count = Signal(self.gp.rob_entries_bits + 1)

        with m.If(self.increment.run & ~self.decrement.run):
            m.d.sync += count.eq(count + 1)

        with m.If(self.decrement.run & ~self.increment.run):
            m.d.sync += count.eq(count - 1)

        @def_method(m, self.increment)
        def _():
            pass

        @def_method(m, self.decrement)
        def _():
            return count == 1 & ~self.increment.run

        return m
