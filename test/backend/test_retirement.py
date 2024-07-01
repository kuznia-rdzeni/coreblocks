from coreblocks.interface.layouts import (
    CoreInstructionCounterLayouts,
    ExceptionRegisterLayouts,
    FetchTargetQueueLayouts,
    InternalInterruptControllerLayouts,
)
from coreblocks.backend.retirement import *
from coreblocks.priv.csr.csr_instances import GenericCSRRegisters

from transactron.lib import FIFO, Adapter
from coreblocks.core_structs.rat import FRAT, RRAT
from coreblocks.params import GenParams
from coreblocks.interface.layouts import ROBLayouts, RFLayouts, SchedulerLayouts
from coreblocks.params.configurations import test_core_config

from transactron.testing import *
from collections import deque
import random


class RetirementTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        rob_layouts = self.gen_params.get(ROBLayouts)
        rf_layouts = self.gen_params.get(RFLayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)
        exception_layouts = self.gen_params.get(ExceptionRegisterLayouts)
        ftq_layouts = self.gen_params.get(FetchTargetQueueLayouts)
        interrupt_controller_layouts = self.gen_params.get(InternalInterruptControllerLayouts)
        core_instr_counter_layouts = self.gen_params.get(CoreInstructionCounterLayouts)

        m.submodules.r_rat = self.rat = RRAT(gen_params=self.gen_params)
        m.submodules.f_rat = self.frat = FRAT(gen_params=self.gen_params)
        m.submodules.free_rf_list = self.free_rf = FIFO(
            scheduler_layouts.free_rf_layout, 2**self.gen_params.phys_regs_bits
        )

        m.submodules.mock_rob_peek = self.mock_rob_peek = TestbenchIO(
            Adapter(o=rob_layouts.peek_layout, nonexclusive=True)
        )

        m.submodules.mock_rob_retire = self.mock_rob_retire = TestbenchIO(Adapter())

        m.submodules.mock_rf_free = self.mock_rf_free = TestbenchIO(Adapter(i=rf_layouts.rf_free))

        m.submodules.mock_exception_cause = self.mock_exception_cause = TestbenchIO(
            Adapter(o=exception_layouts.get, nonexclusive=True)
        )
        m.submodules.mock_exception_clear = self.mock_exception_clear = TestbenchIO(Adapter())

        m.submodules.generic_csr = self.generic_csr = GenericCSRRegisters(self.gen_params)
        DependencyContext.get().add_dependency(GenericCSRRegistersKey(), self.generic_csr)

        m.submodules.mock_fetch_continue = self.mock_fetch_continue = TestbenchIO(Adapter(i=ftq_layouts.resume))
        m.submodules.mock_instr_decrement = self.mock_instr_decrement = TestbenchIO(
            Adapter(o=core_instr_counter_layouts.decrement)
        )
        m.submodules.mock_trap_entry = self.mock_trap_entry = TestbenchIO(Adapter())
        m.submodules.mock_async_interrupt_cause = self.mock_async_interrupt_cause = TestbenchIO(
            Adapter(o=interrupt_controller_layouts.interrupt_cause)
        )
        m.submodules.mock_ftq_commit = self.mock_ftq_commit = TestbenchIO(Adapter(i=ftq_layouts.commit))

        m.submodules.retirement = self.retirement = Retirement(
            self.gen_params,
            rob_retire=self.mock_rob_retire.adapter.iface,
            rob_peek=self.mock_rob_peek.adapter.iface,
            r_rat_commit=self.rat.commit,
            r_rat_peek=self.rat.peek,
            free_rf_put=self.free_rf.write,
            rf_free=self.mock_rf_free.adapter.iface,
            exception_cause_get=self.mock_exception_cause.adapter.iface,
            exception_cause_clear=self.mock_exception_clear.adapter.iface,
            frat_rename=self.frat.rename,
            fetch_continue=self.mock_fetch_continue.adapter.iface,
            instr_decrement=self.mock_instr_decrement.adapter.iface,
            trap_entry=self.mock_trap_entry.adapter.iface,
            async_interrupt_cause=self.mock_async_interrupt_cause.adapter.iface,
            ftq_commit=self.mock_ftq_commit.adapter.iface,
        )

        m.submodules.free_rf_fifo_adapter = self.free_rf_adapter = TestbenchIO(AdapterTrans(self.free_rf.read))

        precommit = DependencyContext.get().get_dependency(InstructionPrecommitKey())
        m.submodules.precommit_adapter = self.precommit_adapter = TestbenchIO(AdapterTrans(precommit))

        return m


# TODO: write a proper retirement test
class TestRetirement(TestCaseWithSimulator):
    def setup_method(self):
        self.gen_params = GenParams(test_core_config)
        self.rf_exp_q = deque()
        self.rat_map_q = deque()
        self.submit_q = deque()
        self.rf_free_q = deque()
        self.precommit_q = deque()

        random.seed(8)
        self.cycles = 256

        rat_state = [0] * self.gen_params.isa.reg_cnt

        for _ in range(self.cycles):
            rl = random.randrange(self.gen_params.isa.reg_cnt)
            rp = random.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
            rob_id = random.randrange(2**self.gen_params.rob_entries_bits)
            if rl != 0:
                if rat_state[rl] != 0:  # phys reg 0 shouldn't be marked as free
                    self.rf_exp_q.append(rat_state[rl])
                self.rf_free_q.append(rat_state[rl])
                rat_state[rl] = rp
                self.rat_map_q.append({"rl_dst": rl, "rp_dst": rp})
                self.submit_q.append({"rob_data": {"rl_dst": rl, "rp_dst": rp}, "rob_id": rob_id, "exception": 0})
                self.precommit_q.append(rob_id)
            # note: overwriting with the same rp or having duplicate nonzero rps in rat shouldn't happen in reality
            # (and the retirement code doesn't have any special behaviour to handle these cases), but in this simple
            # test we don't care to make sure that the randomly generated inputs are correct in this way.

    @def_method_mock(lambda self: self.retc.mock_rob_retire, enable=lambda self: bool(self.submit_q), sched_prio=1)
    def retire_process(self):
        self.submit_q.popleft()

    @def_method_mock(lambda self: self.retc.mock_rob_peek, enable=lambda self: bool(self.submit_q))
    def peek_process(self):
        return self.submit_q[0]

    def free_reg_process(self):
        while self.rf_exp_q:
            reg = yield from self.retc.free_rf_adapter.call()
            assert reg["reg_id"] == self.rf_exp_q.popleft()

    def rat_process(self):
        while self.rat_map_q:
            current_map = self.rat_map_q.popleft()
            wait_cycles = 0
            # this test waits for next rat pair to be correctly set and will timeout if that assignment fails
            while (yield self.retc.rat.entries[current_map["rl_dst"]]) != current_map["rp_dst"]:
                wait_cycles += 1
                if wait_cycles >= self.cycles + 10:
                    assert False, "RAT entry was not updated"
                yield
        assert not self.submit_q
        assert not self.rf_free_q

    def precommit_process(self):
        yield from self.retc.precommit_adapter.call_init()
        while self.precommit_q:
            yield
            info = yield from self.retc.precommit_adapter.call_result()
            assert info is not None
            assert info["side_fx"]
            assert self.precommit_q[0] == info["rob_id"]
            self.precommit_q.popleft()

    @def_method_mock(lambda self: self.retc.mock_rf_free, sched_prio=2)
    def rf_free_process(self, reg_id):
        assert reg_id == self.rf_free_q.popleft()

    @def_method_mock(lambda self: self.retc.mock_exception_cause)
    def exception_cause_process(self):
        return {"cause": 0, "rob_id": 0}  # keep exception cause method enabled

    @def_method_mock(lambda self: self.retc.mock_exception_clear)
    def exception_clear_process(self):
        pass

    @def_method_mock(lambda self: self.retc.mock_instr_decrement)
    def instr_decrement_process(self):
        return {"empty": 0}

    @def_method_mock(lambda self: self.retc.mock_trap_entry)
    def mock_trap_entry_process(self):
        pass

    @def_method_mock(lambda self: self.retc.mock_fetch_continue)
    def mock_fetch_continue_process(self):
        pass

    @def_method_mock(lambda self: self.retc.mock_async_interrupt_cause)
    def mock_async_interrupt_cause(self):
        return {"cause": 0}

    @def_method_mock(lambda self: self.retc.mock_ftq_commit)
    def mock_ftq_commit(self, arg):
        pass

    def test_rand(self):
        self.retc = RetirementTestCircuit(self.gen_params)
        with self.run_simulation(self.retc) as sim:
            sim.add_sync_process(self.free_reg_process)
            sim.add_sync_process(self.rat_process)
            sim.add_sync_process(self.precommit_process)
