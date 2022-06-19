from coreblocks.retirement import *

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import FIFO, Adapter, AdapterTrans
from coreblocks.rat import RAT
from coreblocks.layouts import ROBLayouts
from coreblocks.genparams import GenParams

from .common import *
from collections import deque
import random


class RetirementTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        rob_layouts = self.gen_params.get(ROBLayouts)

        m.submodules.r_rat = self.rat = RAT(gen_params=self.gen_params)
        m.submodules.free_rf_list = self.free_rf = FIFO(
            self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits
        )

        m.submodules.mock_rob_retire = self.mock_rob_retire = TestbenchIO(Adapter(o=rob_layouts.data_layout))

        m.submodules.retirement = self.retirement = Retirement(
            self.mock_rob_retire.adapter.iface, self.rat.commit, self.free_rf.write
        )

        m.submodules.free_rf_fifo_adapter = self.free_rf_adapter = TestbenchIO(AdapterTrans(self.free_rf.read))

        return tm


class RetirementTest(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams("rv32i")
        self.rf_exp_q = deque()
        self.rat_map_q = deque()
        self.submit_q = deque()

        random.seed(8)
        cycles = 256

        rat_state = [0 for _ in range(self.gen_params.isa.reg_cnt)]

        for _ in range(cycles):
            rl = random.randint(0, self.gen_params.isa.reg_cnt - 1)
            rp = random.randint(1, 2**self.gen_params.phys_regs_bits - 1) if rl != 0 else 0
            if rl != 0:
                if rat_state[rl] != 0:  # phys reg 0 shouldn't be marked as free
                    self.rf_exp_q.append(rat_state[rl])
                rat_state[rl] = rp
                self.rat_map_q.append({"rl_dst": rl, "rp_dst": rp})
                self.submit_q.append({"rl_dst": rl, "rp_dst": rp})
            # note: overwriting with the same rp or havng duplicate nonzero rps in rat shouldn't happen in reality
            # (and the retirement code doesn't have any special behaviour in these cases), but in this simple test
            # we don't care to make sure that the randomly generated inputs are correct in this way.

    def test_rand(self):
        retc = RetirementTestCircuit(self.gen_params)

        def submit_process():
            while len(self.submit_q):
                yield from retc.mock_rob_retire.call(self.submit_q.popleft())

        def free_reg_process():
            while len(self.rf_exp_q):
                reg = yield from retc.free_rf_adapter.call()
                self.assertEqual(reg["data"], self.rf_exp_q.popleft())

        def rat_process():
            while len(self.rat_map_q):
                current_map = self.rat_map_q.popleft()
                # this test waits for next rat pair to be correctly set and will timeout if that assignment fails
                while (yield retc.rat.entries[current_map["rl_dst"]]) != current_map["rp_dst"]:
                    yield

        with self.runSimulation(retc) as sim:
            sim.add_sync_process(submit_process)
            sim.add_sync_process(free_reg_process)
            sim.add_sync_process(rat_process)
