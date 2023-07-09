from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.stages.retirement import *
from coreblocks.structs_common.csr_generic import GenericCSRRegisters

from transactron.lib import FIFO, Adapter
from coreblocks.structs_common.rat import RRAT
from coreblocks.params import (
    ROBLayouts,
    RFLayouts,
    GenParams,
    LSULayouts,
    SchedulerLayouts,
)
from coreblocks.params.configurations import test_core_config

from ..common import *
from collections import deque
import random


class RetirementTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        rob_layouts = self.gen_params.get(ROBLayouts)
        rf_layouts = self.gen_params.get(RFLayouts)
        lsu_layouts = self.gen_params.get(LSULayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)
        exception_layouts = self.gen_params.get(ExceptionRegisterLayouts)

        m.submodules.r_rat = self.rat = RRAT(gen_params=self.gen_params)
        m.submodules.free_rf_list = self.free_rf = FIFO(
            scheduler_layouts.free_rf_layout, 2**self.gen_params.phys_regs_bits
        )

        m.submodules.mock_rob_peek = self.mock_rob_peek = TestbenchIO(Adapter(o=rob_layouts.peek_layout))

        m.submodules.mock_rob_retire = self.mock_rob_retire = TestbenchIO(Adapter(o=rob_layouts.retire_layout))

        m.submodules.mock_rob_get_indices = self.mock_rob_get_indices = TestbenchIO(Adapter(o=rob_layouts.get_indices))

        m.submodules.mock_rf_free = self.mock_rf_free = TestbenchIO(Adapter(i=rf_layouts.rf_free))

        m.submodules.mock_precommit = self.mock_precommit = TestbenchIO(Adapter(i=lsu_layouts.precommit))

        m.submodules.mock_exception_cause = self.mock_exception_cause = TestbenchIO(Adapter(o=exception_layouts.get))
        m.submodules.generic_csr = self.generic_csr = GenericCSRRegisters(self.gen_params)
        self.gen_params.get(DependencyManager).add_dependency(GenericCSRRegistersKey(), self.generic_csr)

        m.submodules.retirement = self.retirement = Retirement(
            self.gen_params,
            rob_retire=self.mock_rob_retire.adapter.iface,
            rob_peek=self.mock_rob_peek.adapter.iface,
            r_rat_commit=self.rat.commit,
            free_rf_put=self.free_rf.write,
            rf_free=self.mock_rf_free.adapter.iface,
            precommit=self.mock_precommit.adapter.iface,
            exception_cause_get=self.mock_exception_cause.adapter.iface,
            rob_get_indices=self.mock_rob_get_indices.adapter.iface,
        )

        m.submodules.stall = self.stall = TestbenchIO(AdapterTrans(self.retirement.stall))
        m.submodules.unstall = self.unstall = TestbenchIO(AdapterTrans(self.retirement.unstall))

        m.submodules.free_rf_fifo_adapter = self.free_rf_adapter = TestbenchIO(AdapterTrans(self.free_rf.read))

        return m


class RetirementTest(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams(test_core_config)
        self.rf_exp_q = deque()
        self.rat_map_q = deque()
        self.submit_q = deque()
        self.rf_free_q = deque()
        self.precommit_q = deque()
        self.done_q = deque()

        random.seed(8)
        self.cycles = 256
        self.stalled = False

        rat_state = [0] * self.gen_params.isa.reg_cnt

        for _ in range(self.cycles):
            rl = random.randrange(self.gen_params.isa.reg_cnt)
            rp = random.randrange(1, 2**self.gen_params.phys_regs_bits) if rl != 0 else 0
            pc = random.randrange(0, 2**self.gen_params.isa.xlen)
            rob_id = random.randrange(2**self.gen_params.rob_entries_bits)
            if rl != 0:
                if rat_state[rl] != 0:  # phys reg 0 shouldn't be marked as free
                    self.rf_exp_q.append(rat_state[rl])
                self.rf_free_q.append(rat_state[rl])
                rat_state[rl] = rp
                self.rat_map_q.append({"rl_dst": rl, "rp_dst": rp})
                self.submit_q.append(
                    {"rob_data": {"rl_dst": rl, "rp_dst": rp, "pc": pc}, "rob_id": rob_id, "exception": 0}
                )
                self.precommit_q.append(rob_id)
                # done_q contains amount of precommit calls needed per each instruction in unary form,
                # i.e. [False, True, False, False, False, True] means first instruction needs one precommit
                # call to become "done" and third instruction needs three precommit calls
                for _ in range(random.randrange(1, 6)):
                    self.done_q.append(False)
                self.done_q.append(True)
            # note: overwriting with the same rp or having duplicate nonzero rps in rat shouldn't happen in reality
            # (and the retirement code doesn't have any special behaviour to handle these cases), but in this simple
            # test we don't care to make sure that the randomly generated inputs are correct in this way.
        self.rob_max_id = len(self.precommit_q)

    def test_rand(self):
        retc = RetirementTestCircuit(self.gen_params)

        @def_method_mock(
            lambda: retc.mock_rob_retire, enable=lambda: bool(self.submit_q) and self.done_q[0], sched_prio=1
        )
        def retire_process():
            return self.submit_q.popleft()

        # TODO: mocking really seems to dislike nonexclusive methods for some reason
        @def_method_mock(lambda: retc.mock_rob_peek, enable=lambda: bool(self.submit_q))
        def peek_process():
            return self.submit_q[0]

        def free_reg_process():
            while self.rf_exp_q:
                reg = yield from retc.free_rf_adapter.call()
                self.assertEqual(reg["reg_id"], self.rf_exp_q.popleft())

        def rat_process():
            while self.rat_map_q:
                current_map = self.rat_map_q.popleft()
                wait_cycles = 0
                # this test waits for next rat pair to be correctly set and will timeout if that assignment fails
                while (yield retc.rat.entries[current_map["rl_dst"]]) != current_map["rp_dst"]:
                    wait_cycles += 1
                    if wait_cycles >= self.cycles + 10:
                        self.fail("RAT entry was not updated")
                    yield
            self.assertFalse(self.submit_q)
            self.assertFalse(self.rf_free_q)

        def random_stall():
            yield Passive()
            while True:
                if random.random() < 0.05:
                    while (yield from retc.stall.call())["stalled"] != 1:
                        yield
                    self.stalled = True
                    for _ in range(random.randint(0, 20)):
                        yield
                    yield from retc.unstall.call()
                    self.stalled = False
                else:
                    yield

        @def_method_mock(lambda: retc.mock_rf_free, sched_prio=3)
        def rf_free_process(reg_id):
            self.assertEqual(reg_id, self.rf_free_q.popleft())

        # mock_precommit mock must run later (thus have higher sched_prio)
        # than mock_rob_get_indices because of interdependency on precommit_q
        @def_method_mock(lambda: retc.mock_precommit, sched_prio=4)
        def precommit_process(rob_id):
            self.assertFalse(self.stalled)
            if self.done_q.popleft():
                self.assertEqual(rob_id, self.precommit_q.popleft())

        @def_method_mock(lambda: retc.mock_rob_get_indices, sched_prio=3)
        def rob_get_indices_process():
            start_idx = (self.rob_max_id - len(self.precommit_q)) % 2**self.gen_params.rob_entries_bits
            # end ptr is not used by retirement
            return {"start": start_idx, "end": 0}

        @def_method_mock(lambda: retc.mock_exception_cause)
        def exception_cause_process():
            return {"cause": 0, "rob_id": 0}  # keep exception cause method enabled

        with self.run_simulation(retc) as sim:
            sim.add_sync_process(retire_process)
            sim.add_sync_process(peek_process)
            sim.add_sync_process(free_reg_process)
            sim.add_sync_process(rat_process)
            sim.add_sync_process(rf_free_process)
            sim.add_sync_process(precommit_process)
            sim.add_sync_process(exception_cause_process)
            sim.add_sync_process(random_stall)
            sim.add_sync_process(rob_get_indices_process)
