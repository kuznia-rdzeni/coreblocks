from typing import Sequence
import operator
from functools import reduce

from amaranth import *


from transactron.lib import logging
from transactron.lib.metrics import *
from transactron.lib.simultaneous import condition
from transactron.utils import popcount, DependencyContext, MethodStruct
from transactron.utils.assign import AssignArg
from transactron import *

from coreblocks.params import *
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import UnsafeInstructionResolvedKey

log = logging.HardwareLogger("frontend.stall_ctrl")


class StallController(Elaboratable):
    """
    The stall controller is responsible for managing all stall/unstall signals
    that may be triggered in the core and based on them deciding if and where
    the frontend should be resumed.


    Attributes
    ----------
    stall_unsafe : Method
        Signals that the frontend should be stalled because an unsafe (i.e. causing
        difficult to handle side effects) instruction was just fetched.
    stall_exception : Method
        Signals that the frontend should be stalled because of an exception.
    stall_guard : Method
        A non-exclusive method whose readiness denotes if the frontend is currently stalled.
    resume_from_exception: Method
        Signals that the backend handled the exception and the frontend can be resumed.
    redirect_frontend : Method (bodyless)
        A method that will be called when the frontend needs to be redirected. Should be always
        ready.
    """

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)

        self.stall_unsafe = Method()
        self.stall_exception = Method()
        self.stall_guard = Method()
        self.resume_from_exception = Method(i=layouts.resume)
        self._resume_from_unsafe = Method(i=layouts.resume)

        self.redirect_frontend = Method(i=layouts.redirect)

        DependencyContext.get().add_dependency(UnsafeInstructionResolvedKey(), self._resume_from_unsafe)

    def elaborate(self, platform):
        m = TModule()

        stalled_unsafe = Signal()
        stalled_exception = Signal()

        @def_method(m, self.stall_guard, ready=~(stalled_unsafe | stalled_exception), nonexclusive=True)
        def _():
            pass

        with Transaction().body(m):
            log.assertion(m, self.redirect_frontend.ready)

        def resume_combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            # Make sure that there is at most one caller - there can be only one unsafe instruction
            log.assertion(m, popcount(runs) <= 1)
            pcs = [Mux(runs[i], v.pc, 0) for i, v in enumerate(args)]

            return {"pc": reduce(operator.or_, pcs, 0)}

        @def_method(m, self._resume_from_unsafe, nonexclusive=True, combiner=resume_combiner)
        def _(pc):
            log.assertion(m, stalled_unsafe)
            m.d.sync += stalled_unsafe.eq(0)

            with condition(m, nonblocking=True) as branch:
                with branch(~stalled_exception):
                    log.info(m, True, "Resuming from unsafe instruction new_pc=0x{:x}", pc)
                    self.redirect_frontend(m, pc=pc)

        @def_method(m, self.resume_from_exception)
        def _(pc):
            m.d.sync += stalled_unsafe.eq(0)
            m.d.sync += stalled_exception.eq(0)

            log.info(m, True, "Resuming from exception new_pc=0x{:x}", pc)
            self.redirect_frontend(m, pc=pc)

        @def_method(m, self.stall_unsafe)
        def _():
            log.assertion(m, ~stalled_unsafe, "Can't be stalled twice because of an unsafe instruction")
            log.info(m, True, "Stalling the frontend because of an unsafe instruction")
            m.d.sync += stalled_unsafe.eq(1)

        # Fetch can be resumed to unstall from 'unsafe' instructions, and stalled because
        # of exception report, both can happen at any time during normal excecution.
        @def_method(m, self.stall_exception)
        def _():
            log.info(m, ~stalled_exception, "Stalling the frontend because of an exception")
            m.d.sync += stalled_exception.eq(1)

        return m
