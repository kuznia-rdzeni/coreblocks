from amaranth import *

from coreblocks.params import *
from coreblocks.transactions.core import Method, Transaction, def_method


class InterruptCoordinator(Elaboratable):
    def __init__(
        self,
        *,
        gen_params: GenParams,
        r_rat_get_all: Method,
        f_rat_set_all: Method,
        scheduler_clear: Method,
        frontend_clear: Method,
        fu_clear: Method,
        pc_stall: Method,
        pc_verify_branch: Method,
        rob_can_flush: Method,
        rob_flush: Method,
        free_reg_put: Method
    ):
        self.gen_params = gen_params
        self.r_rat_get_all = r_rat_get_all
        self.f_rat_set_all = f_rat_set_all
        self.scheduler_clear = scheduler_clear
        self.frontend_clear = frontend_clear
        self.fu_clear = fu_clear
        self.pc_stall = pc_stall
        self.pc_verify_branch = pc_verify_branch
        self.rob_can_flush = rob_can_flush
        self.rob_flush = rob_flush
        self.free_reg_put = free_reg_put

        self.trigger = Method()
        self.iret = Method()

    def elaborate(self, platform):
        m = Module()
        interrupt = Signal()
        old_pc = Signal(self.gen_params.isa.xlen)
        int_handler_addr = C(0xFE)

        with m.FSM("idle"):
            with m.State("idle"):
                with m.If(interrupt):
                    m.next = "clear"
            with m.State("clear"):
                with Transaction.body():
                    self.f_rat_set_all(m, self.r_rat_get_all(m))
                    self.frontend_clear(m)
                    self.scheduler_clear(m)
                    self.fu_clear(m)
                    self.pc_stall(m)
                    # ...clear other stuff
                    m.next = "flush_rob"
            with m.State("flush_rob"):
                with Transaction.body():
                    with m.If(self.rob_can_flush(m)):
                        reg = self.rob_flush(m)
                        with m.If(reg != 0):
                            self.free_reg_put(m, reg)
                    with m.Else():
                        m.next = "unstall"
            with m.State("unstall"):
                with Transaction.body():
                    m.d.sync += old_pc.eq(self.pc_verify_branch(m, next_pc=int_handler_addr))
                    m.next = "iret"
            with m.State("iret"):
                with Transaction.body(request=~interrupt):
                    self.pc_verify_branch(m, next_pc=old_pc)
                    m.next = "idle"

        @def_method(m, self.trigger)
        def _():
            m.d.comb += interrupt.eq(1)

        @def_method(m, self.iret)
        def _():
            m.d.comb += interrupt.eq(0)

        return m
