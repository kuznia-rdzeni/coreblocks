from amaranth import *

from coreblocks.params import *
from coreblocks.transactions.core import Method, Transaction, def_method, TModule
from coreblocks.params.keys import MretKey


class InterruptCoordinator(Elaboratable):
    def __init__(
        self,
        *,
        gen_params: GenParams,
        r_rat_get_all: Method,
        f_rat_set_all: Method,
        pc_stall: Method,
        pc_verify_branch: Method,
        rob_empty: Method,
        rob_flush: Method,
        rob_peek: Method,
        free_reg_put: Method,
        retirement_stall: Method,
        retirement_unstall: Method
    ):
        self.gen_params = gen_params
        self.r_rat_get_all = r_rat_get_all
        self.f_rat_set_all = f_rat_set_all
        self.pc_stall = pc_stall
        self.pc_verify_branch = pc_verify_branch
        self.rob_empty = rob_empty
        self.rob_flush = rob_flush
        self.rob_peek = rob_peek
        self.free_reg_put = free_reg_put
        self.retirement_stall = retirement_stall
        self.retirement_unstall = retirement_unstall
        self.trigger = Method()
        self.iret = Method()
        self.interrupt = Signal()

        connections = self.gen_params.get(DependencyManager)
        connections.add_dependency(MretKey(), self.iret)

    def elaborate(self, platform):
        m = TModule()
        return_pc = Signal(self.gen_params.isa.xlen)
        int_handler_addr = C(0x100)

        connections = self.gen_params.get(DependencyManager)
        clear_blocks, unifiers = connections.get_dependency(keys.ClearKey())
        for name, unifier in unifiers.items():
            m.submodules[name] = unifier

        with m.FSM("idle"):
            with m.State("idle"):
                with Transaction(name="WaitForInt").body(m, request=self.interrupt):
                    # We can only stall if rob is nonempty because we need PC of
                    # the next instruction (that didn't execute precommit).
                    # The clue here is that to satisfy liveness condition (which basically says
                    # that we need forward progress even if we have interrupt flag raised constantly)
                    # we can't just stall retirement without checking if ROB's empty and wait
                    # for some instruction to arrive if it was (and hence might not be
                    # able proceed due to lack of aforementioned PC). See also:
                    # https://github.com/kuznia-rdzeni/coreblocks/pull/351#discussion_r1209887087
                    with m.If(~self.rob_empty(m)):
                        self.retirement_stall(m)
                        self.pc_stall(m)
                        m.next = "clear"
            with m.State("clear"):
                # rationale for methods below being in a separate state (as opposed
                # to in the "idle" state) is to possibly shorten the scheduling critical
                # path (rob_empty influences retirement_stall which influences transactions
                # in retirement which might influence rob_peek - not sure how its
                # nonexclusivity comes into play here) and also to make sure that the fetcher
                # is stopped before attempting to clear it with clear_blocks
                with Transaction(name="IntClearAll").body(m):
                    self.f_rat_set_all(m, self.r_rat_get_all(m))
                    clear_blocks(m)
                    next_instr = self.rob_peek(m)
                    m.d.sync += return_pc.eq(next_instr.rob_data.pc)
                    m.next = "flush_rob"
            with m.State("flush_rob"):
                with Transaction(name="IntFlushRob").body(m):
                    # TODO: better ROB flushing by rolling back pointer in free-RF-list
                    with m.If(~self.rob_empty(m)):
                        flushed = self.rob_flush(m)
                        with m.If(flushed.rp_dst != 0):
                            self.free_reg_put(m, flushed.rp_dst)
                    with m.Else():
                        m.next = "unstall"
            with m.State("unstall"):
                with Transaction(name="IntUnstall").body(m):
                    self.pc_verify_branch(m, next_pc=int_handler_addr, from_pc=0)
                    self.retirement_unstall(m)
                    m.next = "wait_for_iret"
            with m.State("wait_for_iret"):
                with Transaction(name="IretStallFetch").body(m, request=~self.interrupt):
                    # note: this approach works only because we stall fetching when
                    # we encounter a system instruction (which includes MRET)
                    self.pc_stall(m)
                    m.next = "iret_jump"
            with m.State("iret_jump"):
                with Transaction(name="IretJump").body(m):
                    self.pc_verify_branch(m, next_pc=return_pc, from_pc=0)
                    m.next = "idle"

        # should be called by interrupt controller (CLIC?)
        @def_method(m, self.trigger, ready=~self.interrupt)
        def _():
            m.d.sync += self.interrupt.eq(1)

        # will get called by FU that handles interrupt return opcodes on precommit
        # (guaranteeing that it happens after all previous instructions have retired)
        @def_method(m, self.iret)
        def _():
            m.d.sync += self.interrupt.eq(0)

        self.trigger.add_conflict(self.iret)

        return m
