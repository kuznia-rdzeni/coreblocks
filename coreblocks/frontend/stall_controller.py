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
    """Frontend of the core."""

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)

        self.stall_unsafe = Method()
        self.stall_exception = Method()
        self.stall_guard = Method()

        self.redirect_frontend = Method(i=layouts.redirect)

        self.resume_from_exception = Method(i=layouts.resume)
        self._resume_from_unsafe = Method(i=layouts.resume)

        DependencyContext.get().add_dependency(UnsafeInstructionResolvedKey(), self._resume_from_unsafe)

        self.perf_exception_stall_duration = FIFOLatencyMeasurer(
            "frontend.ftq.exception_stall_duration",
            description="Duration of stalls caused by exceptions",
            slots_number=1,
            max_latency=4095,
        )
        self.perf_unsafe_stall_duration = FIFOLatencyMeasurer(
            "frontend.ftq.unsafe_stall_duration",
            description="Duration of stalls caused by unsafe instructions",
            slots_number=1,
            max_latency=4095,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_exception_stall_duration, self.perf_unsafe_stall_duration]

        stalled_unsafe = Signal()
        stalled_exception = Signal()

        @def_method(m, self.stall_guard, ready=~(stalled_unsafe | stalled_exception), nonexclusive=True)
        def _():
            pass

        def resume_combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            # Make sure that there is at most one caller
            log.assertion(m, popcount(runs) <= 1)
            pcs = [Mux(runs[i], v.pc, 0) for i, v in enumerate(args)]

            return {"pc": reduce(operator.or_, pcs, 0)}

        @def_method(m, self._resume_from_unsafe, nonexclusive=True, combiner=resume_combiner)
        def _(pc):
            log.assertion(m, stalled_unsafe)
            m.d.sync += stalled_unsafe.eq(0)

            """
            with condition(m, nonblocking=True) as branch:
                with branch(stalled_unsafe):
                    self.perf_unsafe_stall_duration.stop(m)
            with condition(m, nonblocking=True) as branch:
                with branch(from_exception):
                    self.perf_exception_stall_duration.stop(m)
            """

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
            log.assertion(
                m,
                ~stalled_exception,
                "Trying to stall because of an unsafe instruction while being stalled because of an exception",
            )
            log.info(m, True, "Stalling the frontend because of an unsafe instruction")
            # self.perf_unsafe_stall_duration.start(m)
            m.d.sync += stalled_unsafe.eq(1)

        # Fetch can be resumed to unstall from 'unsafe' instructions, and stalled because
        # of exception report, both can happen at any time during normal excecution.
        @def_method(m, self.stall_exception)
        def _():
            log.info(m, ~stalled_exception, "Stalling the frontend because of an exception")
            # with condition(m, nonblocking=True) as branch:
            #    with branch(~stalled_exception):
            #        self.perf_exception_stall_duration.start(m)
            m.d.sync += stalled_exception.eq(1)

        return m
