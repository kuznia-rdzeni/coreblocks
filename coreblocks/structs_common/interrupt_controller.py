from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.genparams import GenParams
from coreblocks.params.keys import AsyncInterruptInsertSignalKey, MretKey

from transactron.core import Method, TModule, def_method


class InterruptController(Elaboratable):
    def __init__(self, gp: GenParams):
        dm = gp.get(DependencyManager)

        self.interrupt_insert = Signal()
        dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.report_interrupt = Method()

        self.mret = Method()
        dm.add_dependency(MretKey(), self.mret)

        self.entry = Method()

    def elaborate(self, platform):
        m = TModule()

        interrupts_enabled = Signal()

        interrupt_pending = Signal()
        m.d.comb += self.interrupt_insert.eq(interrupt_pending & interrupts_enabled)

        @def_method(m, self.report_interrupt)
        def _():
            m.d.sync += interrupt_pending.eq(1)

        @def_method(m, self.mret)
        def _():
            m.d.sync += interrupts_enabled.eq(1)

        @def_method(m, self.entry)
        def _():
            m.d.sync += interrupt_pending.eq(0)
            m.d.sync += interrupts_enabled.eq(0)

        return m
