from coreblocks.backend.retirement import *
from coreblocks.priv.csr.csr_instances import GenericCSRRegisters

from transactron.lib import FIFO, Adapter
from coreblocks.core_structs.rat import FRAT, RRAT
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.lib.adapters import AdapterTrans

from transactron.testing import *
from collections import deque
import random


class RetirementTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = TModule()

        m.submodules.r_rat = self.rat = RRAT(gen_params=self.gen_params)
        m.submodules.f_rat = self.frat = FRAT(gen_params=self.gen_params)
        m.submodules.free_rf_list = self.free_rf = FIFO(
            [("ident", range(self.gen_params.phys_regs))], self.gen_params.phys_regs
        )

        m.submodules.generic_csr = self.generic_csr = GenericCSRRegisters(self.gen_params)
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.generic_csr)

        m.submodules.retirement = self.retirement = Retirement(self.gen_params)

        self.retirement.r_rat_commit.proxy(m, self.rat.commit)
        self.retirement.r_rat_peek.proxy(m, self.rat.peek)
        self.retirement.free_rf_put.proxy(m, self.free_rf.write)
        self.retirement.f_rat_rename.proxy(m, self.frat.rename)

        m.submodules.mock_rob_peek = self.mock_rob_peek = TestbenchIO(
            Adapter(self.retirement.rob_peek, nonexclusive=True)
        )
        m.submodules.mock_rob_retire = self.mock_rob_retire = TestbenchIO(Adapter(self.retirement.rob_retire))
        m.submodules.mock_rf_free = self.mock_rf_free = TestbenchIO(Adapter(self.retirement.rf_free))
        m.submodules.mock_exception_cause = self.mock_exception_cause = TestbenchIO(
            Adapter(self.retirement.exception_cause_get, nonexclusive=True)
        )
        m.submodules.mock_exception_clear = self.mock_exception_clear = TestbenchIO(
            Adapter(self.retirement.exception_cause_clear)
        )
        m.submodules.mock_fetch_continue = self.mock_fetch_continue = TestbenchIO(
            Adapter(self.retirement.fetch_continue)
        )
        m.submodules.mock_instr_decrement = self.mock_instr_decrement = TestbenchIO(
            Adapter(self.retirement.instr_decrement)
        )
        m.submodules.mock_trap_entry = self.mock_trap_entry = TestbenchIO(Adapter(self.retirement.trap_entry))
        m.submodules.mock_async_interrupt_cause = self.mock_async_interrupt_cause = TestbenchIO(
            Adapter(self.retirement.async_interrupt_cause)
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

    @def_method_mock(lambda self: self.retc.mock_rob_retire, enable=lambda self: bool(self.submit_q))
    def retire_process(self):
        @MethodMock.effect
        def eff():
            self.submit_q.popleft()

    @def_method_mock(lambda self: self.retc.mock_rob_peek, enable=lambda self: bool(self.submit_q))
    def peek_process(self):
        return self.submit_q[0]

    async def free_reg_process(self, sim: TestbenchContext):
        while self.rf_exp_q:
            reg = await self.retc.free_rf_adapter.call(sim)
            assert reg["ident"] == self.rf_exp_q.popleft()

    async def rat_process(self, sim: TestbenchContext):
        while self.rat_map_q:
            current_map = self.rat_map_q.popleft()
            wait_cycles = 0
            # this test waits for next rat pair to be correctly set and will timeout if that assignment fails
            while sim.get(self.retc.rat.entries[current_map["rl_dst"]]) != current_map["rp_dst"]:
                wait_cycles += 1
                if wait_cycles >= self.cycles + 10:
                    assert False, "RAT entry was not updated"
                await sim.tick()
        assert not self.submit_q
        assert not self.rf_free_q

    async def precommit_process(self, sim: TestbenchContext):
        while self.precommit_q:
            info = await self.retc.precommit_adapter.call_try(sim, rob_id=self.precommit_q[0])
            assert info is not None
            assert info["side_fx"]
            self.precommit_q.popleft()

    @def_method_mock(lambda self: self.retc.mock_rf_free)
    def rf_free_process(self, reg_id):
        @MethodMock.effect
        def eff():
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
    def mock_fetch_continue_process(self, pc):
        pass

    @def_method_mock(lambda self: self.retc.mock_async_interrupt_cause)
    def mock_async_interrupt_cause(self):
        return {"cause": 0}

    def test_rand(self):
        self.retc = RetirementTestCircuit(self.gen_params)
        with self.run_simulation(self.retc) as sim:
            sim.add_testbench(self.free_reg_process)
            sim.add_testbench(self.rat_process)
            sim.add_testbench(self.precommit_process)
