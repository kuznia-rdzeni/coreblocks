from amaranth import *

from coreblocks.transactions.core import Method, Transaction, def_method

class InterruptCoordinator(Elaboratable):
    def __init__(self, r_rat_get_all: Method, f_rat_set_all: Method, sched_clear: Method):
        self.trigger = Method()
        self.r_rat_get_all= r_rat_get_all
        self.f_rat_set_all = f_rat_set_all
        self.sched_clear = sched_clear

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.trigger)
        def _():
            self.f_rat_set_all(m, self.r_rat_get_all(m))
            self.sched_clear(m)

        return m
