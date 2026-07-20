from typing import Sequence

from amaranth import *

from transactron.utils import OneHotMux, logging
from transactron.lib.metrics import *
from transactron.utils import popcount, DependencyContext, MethodStruct
from transactron.utils.assign import AssignArg
from transactron import *

from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import CoreStateKey, UnsafeInstructionResolvedKey

log = logging.HardwareLogger("frontend.stall_ctrl")


class StallController(Elaboratable):
    """
    The stall controller is responsible for managing all stall/unstall signals
    that may be triggered in the core and based on them deciding if and where
    the frontend should be resumed.
    """

    stall_unsafe: Provided[Method]
    """
    Signals that the frontend should be stalled because an unsafe (i.e. causing
    difficult to handle side effects) instruction was just fetched.
    """

    stall_guard: Provided[Method]
    """A non-exclusive method whose readiness denotes if the frontend is currently stalled."""

    resume_from_exception: Provided[Method]
    """Signals that the backend handled the exception and the frontend can be resumed."""

    redirect_frontend: Required[Method]
    """A method that will be called when the frontend needs to be redirected. Should be always ready."""

    get_exception_information: Required[Method]
    """Gets information from `ExceptionInformationRegister`."""

    frontend_flush: Required[Method]

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        self.stall_unsafe = Method()
        self.stall_guard = Method()

        self.frontend_flush = Method()

        self.on_redirect_frontend = Method()

        self.get_exception_information = Method(o=gen_params.get(ExceptionInformationRegisterLayouts).get)

        layouts = gen_params.get(FetchLayouts)

        self.redirect_frontend = Method(i=layouts.backend_redirect)
        self._resume_from_unsafe = Method(i=layouts.backend_redirect)

        self.dm = DependencyContext.get()

        self.dm.add_dependency(UnsafeInstructionResolvedKey(), self._resume_from_unsafe)

    def elaborate(self, platform):
        m = TModule()

        with Transaction().body(m):
            core_state = self.dm.get_dependency(CoreStateKey())(m)

        # Fetch can be resumed to unstall from 'unsafe' instructions, and stalled because
        # of exception report, both can happen at any time during normal execution.
        stalled_unsafe = Signal()
        stalled_exception = Signal()

        @def_method(m, self.stall_guard, ready=~(stalled_unsafe | stalled_exception), nonexclusive=True)
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

        def resume_combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            # Make sure that there is at most one caller - there can be only one unsafe instruction
            log.assertion(m, popcount(runs) <= 1)
            return OneHotMux.create(m, [(runs[i], args[i]) for i in range(len(args))])

        @def_method(m, self._resume_from_unsafe, nonexclusive=True, combiner=resume_combiner)
        def _(ftq_ptr, pc):
            log.info(m, True, "Unsafe instruction resolved to pc=0x{:x}", pc)

            self.redirect_frontend(m, ftq_ptr=ftq_ptr, pc=pc)

        @def_method(m, self.on_redirect_frontend)
        def _():
            # All redirections change execuction point so clear unsafe state
            log.assertion(m, ~self.stall_guard.ready, "Frontend needs to be stalled for a redirect")
            m.d.sync += stalled_unsafe.eq(0)

        @def_method(m, self.stall_unsafe)
        def _():
            log.assertion(m, ~stalled_unsafe, "Can't be stalled twice because of an unsafe instruction")
            log.info(m, True, "Stalling frontend - unsafe instruction")
            m.d.sync += stalled_unsafe.eq(1)

        return m
