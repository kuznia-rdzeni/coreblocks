from amaranth import *
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import FetchLayouts
from transactron.core import Method, TModule, def_method


class CoreInstructionCounter(Elaboratable):
    def __init__(self, gp: GenParams):
        self.increment = Method(i=gp.get(FetchLayouts).raw_instr)
        self.decrement = Method(o=[("empty", 1)])

        self.count = Signal(gp.rob_entries_bits + 1)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        with m.If(self.increment.run & ~self.decrement.run):
            m.d.sync += self.count.eq(self.count + 1)

        with m.If(self.decrement.run & ~self.increment.run):
            m.d.sync += self.count.eq(self.count - 1)

        @def_method(m, self.increment)
        def _(instr, rvc, access_fault, pc):
            pass

        @def_method(m, self.decrement)
        def _():
            return self.count == 1 & ~self.increment.run

        return m
