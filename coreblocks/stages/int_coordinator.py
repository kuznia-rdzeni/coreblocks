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
        pc_stall: Method,
        pc_verify_branch: Method,
        rob_can_flush: Method,
        rob_flush: Method,
        free_reg_put: Method
    ):
        self.gen_params = gen_params
        self.r_rat_get_all = r_rat_get_all
        self.f_rat_set_all = f_rat_set_all
        self.pc_stall = pc_stall
        self.pc_verify_branch = pc_verify_branch
        self.rob_can_flush = rob_can_flush
        self.rob_flush = rob_flush
        self.free_reg_put = free_reg_put
        self.trigger = Method()
        self.iret = Method()
        self.allow_retirement = Signal(reset=1)
        self.interrupt = Signal()

    def elaborate(self, platform):
        m = Module()
        old_pc = Signal(self.gen_params.isa.xlen)
        int_handler_addr = C(0x100)

        connections = self.gen_params.get(DependencyManager)
        clear_blocks, unifiers = connections.get_dependency(keys.ClearKey())
        for name, unifier in unifiers.items():
            m.submodules[name] = unifier

        with m.FSM("idle"):
            with m.State("idle"):
                with m.If(self.interrupt):
                    m.d.sync += self.allow_retirement.eq(0)
                    m.next = "clear"
            with m.State("clear"):
                with Transaction(name="IntClearAll").body(m):
                    self.f_rat_set_all(m, self.r_rat_get_all(m))
                    self.pc_stall(m)
                    clear_blocks(m)
                    m.next = "flush_rob"
            with m.State("flush_rob"):
                with Transaction(name="IntFlushRob").body(m):
                    with m.If(self.rob_can_flush(m)):
                        reg = self.rob_flush(m)
                        with m.If(reg != 0):
                            self.free_reg_put(m, reg.rp_dst)
                    with m.Else():
                        m.next = "unstall"
            with m.State("unstall"):
                with Transaction(name="IntUnstall").body(m):
                    m.d.sync += old_pc.eq(self.pc_verify_branch(m, next_pc=int_handler_addr))
                    m.d.sync += self.allow_retirement.eq(1)
                    m.next = "iret"
            with m.State("iret"):
                with m.If(~self.interrupt):
                    m.next = "idle"

        # should be called by interrupt controller (CLIC?)
        @def_method(m, self.trigger)
        def _():
            m.d.sync += self.interrupt.eq(1)

        # should be called by block responsible for handling mret (FU?)
        @def_method(m, self.iret)
        def _():
            m.d.sync += self.interrupt.eq(0)

        return m
