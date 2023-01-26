from coreblocks.stages.retirement import *

from coreblocks.transactions.lib import FIFO, Adapter
from coreblocks.structs_common.rat import RRAT
from coreblocks.params import ROBLayouts, RFLayouts
from coreblocks.utils import AutoDebugSignals

from ..common import *
from collections import deque
import random


class RetirementTestCircuit(Elaboratable, AutoDebugSignals):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        rob_layouts = self.gen_params.get(ROBLayouts)
        rf_layouts = self.gen_params.get(RFLayouts)

        m.submodules.r_rat = self.rat = RRAT(gen_params=self.gen_params)
        m.submodules.free_rf_list = self.free_rf = FIFO(
            self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits
        )

        m.submodules.mock_rob_retire = self.mock_rob_retire = TestbenchIO(Adapter(o=rob_layouts.data_layout))

        m.submodules.mock_rf_free = self.mock_rf_free = TestbenchIO(Adapter(i=rf_layouts.rf_free))

        m.submodules.retirement = self.retirement = Retirement(
            rob_retire=self.mock_rob_retire.adapter.iface,
            r_rat_commit=self.rat.commit,
            free_rf_put=self.free_rf.write,
            rf_free=self.mock_rf_free.adapter.iface,
        )

        m.submodules.free_rf_fifo_adapter = self.free_rf_adapter = TestbenchIO(AdapterTrans(self.free_rf.read))

        return tm


class RetirementTest(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = test_gen_params("rv32i")
        self.rf_exp_q = deque()
        self.rat_map_q = deque()
        self.submit_q = deque()
        self.rf_free_q = deque()

        random.seed(8)
        self.cycles = 256

        rat_state = [0 for _ in range(self.gen_params.isa.reg_cnt)]

        for _ in range(self.cycles):
            rl = random.randint(0, self.gen_params.isa.reg_cnt - 1)
            rp = random.randint(1, 2**self.gen_params.phys_regs_bits - 1) if rl != 0 else 0
            if rl != 0:
                if rat_state[rl] != 0:  # phys reg 0 shouldn't be marked as free
                    self.rf_exp_q.append(rat_state[rl])
                self.rf_free_q.append(rat_state[rl])
                rat_state[rl] = rp
                self.rat_map_q.append({"rl_dst": rl, "rp_dst": rp})
                self.submit_q.append({"rl_dst": rl, "rp_dst": rp})
            # note: overwriting with the same rp or having duplicate nonzero rps in rat shouldn't happen in reality
            # (and the retirement code doesn't have any special behaviour to handle these cases), but in this simple
            # test we don't care to make sure that the randomly generated inputs are correct in this way.

    def test_rand(self):
        retc = RetirementTestCircuit(self.gen_params)

        @def_method_mock(lambda: retc.mock_rob_retire, settle=1, condition=lambda: bool(self.submit_q))
        def submit_process(_):
            return self.submit_q.popleft()

        def free_reg_process():
            while self.rf_exp_q:
                reg = yield from retc.free_rf_adapter.call()
                self.assertEqual(reg["data"], self.rf_exp_q.popleft())

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

        @def_method_mock(lambda: retc.mock_rf_free, condition=lambda: bool(self.rf_free_q))
        def rf_free_process(reg):
            self.assertEqual(reg["reg_id"], self.rf_free_q.popleft())

        with self.run_simulation(retc) as sim:
            sim.add_sync_process(submit_process)
            sim.add_sync_process(free_reg_process)
            sim.add_sync_process(rat_process)
            sim.add_sync_process(rf_free_process)
