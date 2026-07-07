from typing import Sequence
import operator
from functools import reduce

from amaranth import *


from transactron.utils import logging
from transactron.lib.metrics import *
from transactron.lib.simultaneous import condition
from transactron.utils import popcount, DependencyContext, MethodStruct
from transactron.utils.assign import AssignArg
from transactron import *

from coreblocks.interface.layouts import ExceptionRegisterLayouts
from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import CoreStateKey, RollbackKey, UnsafeInstructionResolvedKey

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

    stall_exception: Provided[Method]
    """Signals that the frontend should be stalled because of an exception."""

    stall_guard: Provided[Method]
    """A non-exclusive method whose readiness denotes if the frontend is currently stalled."""

    resume_from_core_flush: Provided[Method]
    """Signals that the backend handled the exception and the frontend can be resumed."""

    redirect_frontend: Required[Method]
    """A method that will be called when the frontend needs to be redirected. Should be always ready."""

    fetch_flush: Required[Method]

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)

        self.stall_unsafe = Method()
        self.stall_guard = Method()
        self.resume_from_core_flush = Method(i=layouts.resume)
        self._resume_from_unsafe = Method(i=layouts.resume)

        self.redirect_frontend = Method(i=layouts.frontend_redirect)

        self.dm = DependencyContext.get()
        self.dm.add_dependency(UnsafeInstructionResolvedKey(), self._resume_from_unsafe)
        self.rollback_handler = Method(i=gen_params.get(RATLayouts).rollback_in)
        self.dm.add_dependency(RollbackKey(), self.rollback_handler)

        self.get_exception_information = Method(o=gen_params.get(ExceptionRegisterLayouts).get)
        self.fetch_flush = Method()

    def elaborate(self, platform):
        m = TModule()

        stalled_unsafe = Signal()

        get_core_state = self.dm.get_dependency(CoreStateKey())

        stalled_exception = Signal()
        prev_stalled_exception = Signal()
        with Transaction().body(m):
            m.d.comb += stalled_exception.eq(self.get_exception_information(m).valid | get_core_state(m).flushing)

            log.info(
                m,
                stalled_exception & ~prev_stalled_exception,
                "Stalling fetch because of pending exception on current path",
            )

            # Exception state can be (but doesn't have to) cleared after rollback, that already set the new fetch pc, we can sefely just unblock
            log.info(
                m,
                ~stalled_exception & prev_stalled_exception,
                "Unblocking fetch from exception stall, will resume from last redirect",
            )

        m.d.sync += prev_stalled_exception.eq(stalled_exception)

        with Transaction().body(m, ready=~prev_stalled_exception & stalled_exception):
            self.fetch_flush(m)  # not required for corectness, but removes more unneccessary instructions

        @def_method(m, self.stall_guard, ready=~(stalled_unsafe | stalled_exception), nonexclusive=True)
        def _():
            pass

        def resume_combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            # Make sure that there is at most one caller - there can be only one unsafe instruction
            log.assertion(m, popcount(runs) <= 1)
            pcs = [Mux(runs[i], v.pc, 0) for i, v in enumerate(args)]

            return {"pc": reduce(operator.or_, pcs, 0)}

        @def_method(m, self._resume_from_unsafe, nonexclusive=True, combiner=resume_combiner)
        def _(pc):
            # TODO: wait, why we pass that through forwarder everywhere, isn't it always ready?

            # Instructions must verify tag is active when queuing resume, inactive instructions
            # were unstalled already at rollback (don't do double rollback).
            # Resuming on instructions that will be later invalidated is fine.
            log.assertion(m, stalled_unsafe)

            m.d.sync += stalled_unsafe.eq(0)

            with condition(m, nonblocking=True) as branch:
                with branch(~stalled_exception):
                    log.info(m, True, "Resuming from unsafe instruction new_pc=0x{:x}", pc)
                    self.redirect_frontend(m, pc=pc, from_unsafe=1)

        @def_method(m, self.resume_from_core_flush)
        def _(pc):  # TODO: are there some important confilcts?
            m.d.sync += stalled_unsafe.eq(0)

            log.info(m, True, "Resuming from core flush pc=0x{:x}", pc)

            self.redirect_frontend(m, pc=pc, from_unsafe=0)
            self.fetch_flush(m)  # sort of workaround for now - ifq changes target a cycle after removing guard

        @def_method(m, self.stall_unsafe)
        def _():
            log.assertion(m, ~stalled_unsafe, "Can't be stalled twice because of an unsafe instruction")
            log.info(m, True, "Stalling the frontend because of an unsafe instruction")
            m.d.sync += stalled_unsafe.eq(1)

        @def_method(m, self.rollback_handler)
        def _(tag, pc, ftq_ptr):
            # rollback invalidates prefix of instructions - always clears unsafe state
            m.d.sync += stalled_unsafe.eq(0)
            log.info(m, stalled_unsafe, "Resuming from unsafe state because of rollback")

        return m
