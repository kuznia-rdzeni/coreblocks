from amaranth import *
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.keys import GenericCSRRegistersKey

from transactron.core import Method, Transaction, TModule, def_method
from coreblocks.params.genparams import GenParams
from coreblocks.params.layouts import RetirementLayouts
from coreblocks.structs_common.csr_generic import CSRAddress, DoubleCounterCSR


class Retirement(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        *,
        rob_peek: Method,
        rob_retire: Method,
        rob_get_indices: Method,
        r_rat_commit: Method,
        free_rf_put: Method,
        rf_free: Method,
        precommit: Method,
        exception_cause_get: Method
    ):
        self.gen_params = gen_params
        self.rob_peek = rob_peek
        self.rob_retire = rob_retire
        self.rob_get_indices = rob_get_indices
        self.r_rat_commit = r_rat_commit
        self.free_rf_put = free_rf_put
        self.rf_free = rf_free
        self.precommit = precommit
        self.exception_cause_get = exception_cause_get

        self.stall = Method(o=self.gen_params.get(RetirementLayouts).stall)
        self.unstall = Method()

        self.instret_csr = DoubleCounterCSR(gen_params, CSRAddress.INSTRET, CSRAddress.INSTRETH)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.instret_csr = self.instret_csr

        # start_idx of last instruction that got sent a precommit
        last_precommit_id = Signal(self.gen_params.rob_entries_bits)
        # stall request from outside
        stall_req = Signal()
        imm_stall_req = Signal()
        # stall immediately on this clock cycle or any future ones
        # until stall_req is deasserted (by calling self.unstall)
        stall_cond = imm_stall_req | stall_req

        rob_indices = Record.like(self.rob_get_indices.data_out)
        # did we already send precommit for instruction at the start of the ROB?
        precommit_sent = Signal()
        m.d.comb += precommit_sent.eq(rob_indices.start == last_precommit_id)

        # logic for allowing to execute precommit and retire: there's no stall or there is a
        # stall but we already broadcasted precommit for an instruction at the start of the ROB
        # so we need to retire it because it could've started executing its side effects
        req_precommit = req_retire = ~stall_cond | precommit_sent

        indices_trans = Transaction(name="get_indices")
        precommit_trans = Transaction(name="precommit")
        retire_trans = Transaction(name="retire")

        with indices_trans.body(m):
            m.d.comb += rob_indices.eq(self.rob_get_indices(m))

        @def_method(m, self.stall)
        def _():
            m.d.sync += stall_req.eq(1)
            m.d.comb += imm_stall_req.eq(1)
            return {"stalled": ~precommit_sent}

        @def_method(m, self.unstall, ready=stall_req)
        def _():
            m.d.sync += stall_req.eq(0)

        with precommit_trans.body(m, request=req_precommit):
            # TODO: do we prefer single precommit call per instruction?
            # If so, the precommit method should send an acknowledge signal here.
            # Just calling once is not enough, because the insn might not be in relevant unit yet.
            rob_entry = self.rob_peek(m)
            self.precommit(m, rob_id=rob_entry.rob_id)
            m.d.sync += last_precommit_id.eq(rob_indices.start)

        with retire_trans.body(m, request=req_retire):
            rob_entry = self.rob_retire(m)

            # TODO: Trigger InterruptCoordinator (handle exception) when rob_entry.exception is set.
            with m.If(rob_entry.exception):
                mcause = self.gen_params.get(DependencyManager).get_dependency(GenericCSRRegistersKey()).mcause
                cause = self.exception_cause_get(m).cause
                entry = Signal(self.gen_params.isa.xlen)
                # MSB is exception bit
                m.d.comb += entry.eq(cause | (1 << (self.gen_params.isa.xlen - 1)))
                mcause.write(m, entry)

            # set rl_dst -> rp_dst in R-RAT
            rat_out = self.r_rat_commit(m, rl_dst=rob_entry.rob_data.rl_dst, rp_dst=rob_entry.rob_data.rp_dst)

            self.rf_free(m, rat_out.old_rp_dst)

            # put old rp_dst to free RF list
            with m.If(rat_out.old_rp_dst):  # don't put rp0 to free list - reserved to no-return instructions
                self.free_rf_put(m, rat_out.old_rp_dst)

            self.instret_csr.increment(m)

        self.stall.add_conflict(self.unstall)
        self.stall.schedule_before(precommit_trans)
        self.stall.schedule_before(retire_trans)
        indices_trans.schedule_before(precommit_trans)
        indices_trans.schedule_before(retire_trans)
        indices_trans.schedule_before(self.stall)

        return m
