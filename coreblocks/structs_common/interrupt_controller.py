from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.genparams import GenParams
from coreblocks.params.keys import AsyncInterruptInsertSignalKey

from transactron.core import Method, TModule, def_method


class InterruptController(Elaboratable):
    def __init__(self, gp: GenParams):
        # TODO: Implement maskable and NMI
        # TODO: Multiple interrupts save cause - last interrupt - set at handler enter
        # About mip pending - what if interrupt comes when we clear its flag - but possibly it could be
        # one cycle before and no one would see difference

        self.interrupt_insert = Signal()
        gp.get(DependencyManager).add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.report_interrupt = Method()

    def elaborate(self, platform):
        m = TModule()

        interrupt_pending = Signal()

        m.d.comb += self.interrupt_insert.eq(interrupt_pending)

        @def_method(m, self.report_interrupt)
        def _():
            m.d.comb += self.interrupt_insert.eq(1)
            m.d.sync += interrupt_pending.eq(1)

        return m
