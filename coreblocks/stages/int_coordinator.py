from amaranth import *

from transactron import Method, Transaction, def_method, TModule
from coreblocks.params import *
from coreblocks.params.keys import MretKey
from coreblocks.structs_common.csr import CSRRegister
from coreblocks.structs_common.csr_generic import CSRAddress


class InterruptCoordinator(Elaboratable):
    """
    Module responsible for sequencing interrupt handling. It contains a state
    machine that executes the following steps:
    1. Wait for interrupt method to get called
    2. Wait for ROB to be nonempty (to always have PC of instruction to come
       back to from the ISR) and wait for retirement to stall
    3. Save interrupt return address into MEPC, clear all state in the pipeline
       that could be holding instructions and restore FRAT from RRAT
    4. Flush instructions from ROB, making sure physical registers get recycled
       into Free-RF FIFO
    5. Jump to the ISR and unstall retirement
    6. Wait for interrupt return method to get called
    7. Jump back to the main program flow

    In the current implementation nested interrupts are disallowed.

    Attributes
    ----------
    trigger: Method
        Starts the interrupt processing state machine. Note that an unspecified
        but bounded amount of cycles can happen between calling this method and
        actual processing taking place due to constraints on precise instruction
        retirement (instructions which started executing side effects must get
        retired first).
    iret: Method
        Interrupt return. Triggers return from an ISR to an address held in `mepc`
        Can be called only after `trigger` has been called. Should be called by
        instructions that cause interrupt return - currently only MRET.
    interrupt: Signal
        Flag which indicates that interrupt processing has been requested. Raised
        by calling `trigger`, deasserted by calling `iret` (usually through MRET
        instruction in ISR).
    mepc: CSRRegister
        CSR register which holds the ISR return address.
    mtvec: CSRRegister
        CSR register which holds the interrupt vector. Currently this only
        supports having one ISR.
    """

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

        self.mepc = CSRRegister(CSRAddress.MEPC, self.gen_params, ro_bits=0b1)
        self.mtvec = CSRRegister(CSRAddress.MTVEC, self.gen_params, ro_bits=0b11)

        connections = self.gen_params.get(DependencyManager)
        connections.add_dependency(MretKey(), self.iret)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.mepc = self.mepc
        m.submodules.mtvec = self.mtvec

        connections = self.gen_params.get(DependencyManager)
        clear_blocks, unifiers = connections.get_dependency(keys.ClearKey())
        for name, unifier in unifiers.items():
            m.submodules[name] = unifier

        with m.FSM("idle"):
            with m.State("idle"):
                with Transaction(name="WaitForInt").body(m, request=self.interrupt):
                    with m.If(~self.rob_empty(m) & self.retirement_stall(m)):
                        m.next = "clear"
            with m.State("clear"):
                with Transaction(name="IntClearAll").body(m):
                    # stall fetcher *after* retirement has been stalled
                    # so that no spurious unstall occurs
                    self.pc_stall(m)
                    self.f_rat_set_all(m, self.r_rat_get_all(m))
                    clear_blocks(m)
                    next_instr = self.rob_peek(m)
                    self.mepc.write(m, next_instr.rob_data.pc)
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
                    int_handler_addr = self.mtvec.read(m).data
                    # TODO: do something with placeholder from_pc
                    self.pc_verify_branch(m, next_pc=int_handler_addr, from_pc=0)
                    self.retirement_unstall(m)
                    m.next = "wait_for_iret"
            with m.State("wait_for_iret"):
                with Transaction(name="IretStallFetch").body(m, request=~self.interrupt):
                    # note: this approach works only because we stall fetching when
                    # we encounter a system instruction (which includes MRET)
                    return_pc = self.mepc.read(m).data
                    # TODO: do something with placeholder from_pc
                    self.pc_verify_branch(m, next_pc=return_pc, from_pc=0)
                    m.next = "idle"

        # should be called by interrupt controller (CLIC?)
        # currently we disallow nested interrupts
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
