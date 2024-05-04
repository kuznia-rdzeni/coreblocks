from amaranth import *
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.genparams import GenParams
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, MretKey

from transactron.core import Method, TModule, def_method


class InterruptController(Elaboratable):
    def __init__(self, gp: GenParams):
        dm = DependencyContext.get()

        self.interrupt_insert = Signal()
        dm.add_dependency(AsyncInterruptInsertSignalKey(), self.interrupt_insert)

        self.report_interrupt = Method()

        self.mret = Method()
        dm.add_dependency(MretKey(), self.mret)

        self.entry = Method()

        self.interrupts_enabled = Signal(reset=1)  # Temporarily needed globally accessibletests

    def elaborate(self, platform):
        m = TModule()

        interrupt_pending = Signal()
        m.d.comb += self.interrupt_insert.eq(interrupt_pending & self.interrupts_enabled)

        @def_method(m, self.report_interrupt)
        def _():
            m.d.sync += interrupt_pending.eq(1)

        @def_method(m, self.mret)
        def _():
            m.d.sync += self.interrupts_enabled.eq(1)

        @def_method(m, self.entry)
        def _():
            m.d.sync += interrupt_pending.eq(0)
            m.d.sync += self.interrupts_enabled.eq(0)

        return m
