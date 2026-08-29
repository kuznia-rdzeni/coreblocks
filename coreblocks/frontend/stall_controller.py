from amaranth import *

from transactron.utils import logging
from transactron.lib.metrics import *
from transactron.utils import DependencyContext
from transactron import *

from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import CoreStateKey

log = logging.HardwareLogger("frontend.stall_ctrl")


class StallController(Elaboratable):
    """
    The stall controller watches for exceptions raised on the speculative path and stalls the
    frontend until the backend redirects it to the trap handler (or a rollback invalidates the
    exception and redirects the frontend itself).
    """

    stall_guard: Provided[Method]
    """A non-exclusive method whose readiness denotes if the frontend is currently stalled."""

    get_exception_information: Required[Method]
    """Gets information from `ExceptionInformationRegister`."""

    frontend_flush: Required[Method]

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.stall_guard = Method()

        self.frontend_flush = Method()

        self.get_exception_information = Method(o=gen_params.get(ExceptionInformationRegisterLayouts).get)

        self.dm = DependencyContext.get()

    def elaborate(self, platform):
        m = TModule()

        with Transaction().always_body(m):
            core_state = self.dm.get_dependency(CoreStateKey())(m)

        stalled_exception = Signal()

        @def_method(m, self.stall_guard, ready=~stalled_exception, nonexclusive=True)
        def _():
            pass

        with Transaction().body(m):
            # Treat core flushing as a latched valid exception, all tags will be freed and invalidated during flush
            exception = self.get_exception_information(m)

            with m.If((exception.valid | core_state.flushing) & ~stalled_exception):
                log.debug(m, True, "Stalling frontend - pending exception on speculative path")
                m.d.sync += stalled_exception.eq(1)
                self.frontend_flush(m)

            with m.If(~exception.valid & ~core_state.flushing & stalled_exception):
                # This can happen in two cases:
                # * exception got rolled-back, redirect needs to be called from rollback
                # * retirement finished flushing the core - it will also call the redirect
                log.debug(m, True, "Removing frontend exception stalled state - exception got invalidated")
                m.d.sync += stalled_exception.eq(0)

        return m
