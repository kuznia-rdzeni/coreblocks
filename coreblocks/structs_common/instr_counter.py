from amaranth import *
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import CoreInstructionCounterLayouts
from transactron.core import Method, TModule, def_method


class CoreInstructionCounter(Elaboratable):
    """
    Counts instructions currently processed in core.
    Used in exception handling, to wait for core flush to finsh.
    """

    def __init__(self, gp: GenParams):
        self.increment = Method()
        self.decrement = Method(o=gp.get(CoreInstructionCounterLayouts).decrement)

        self.count = Signal(gp.rob_entries_bits + 1)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        with m.If(self.increment.run & ~self.decrement.run):
            m.d.sync += self.count.eq(self.count + 1)

        with m.If(self.decrement.run & ~self.increment.run):
            m.d.sync += self.count.eq(self.count - 1)

        @def_method(m, self.increment)
        def _():
            pass

        @def_method(m, self.decrement)
        def _():
            return self.count == 1 & ~self.increment.run

        return m
