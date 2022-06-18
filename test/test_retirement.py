from coreblocks.retirement import *

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import FIFO, Adapter, AdapterTrans
from coreblocks.rat import RAT
from coreblocks.layouts import ROBLayouts
from coreblocks.genparams import GenParams

from .common import *
import queue
import random


class RetirementTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        rob_layouts = self.gen_params.get(ROBLayouts)

        with tm.transactionContext():

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
        self.rf_exp_q = queue.Queue()
        self.rat_map_q = queue.Queue()
        self.submit_q = queue.Queue()

        random.seed(8)
        cycles = 256

        rat_state = [0 for _ in range(self.gen_params.isa.reg_cnt)]

        for _ in range(cycles):
            rl = random.randint(0, self.gen_params.isa.reg_cnt - 1)
            rp = random.randint(1, 2**self.gen_params.phys_regs_bits - 1) if rl != 0 else 0
            if rl != 0:
                if rat_state[rl] != 0:  # phys reg 0 shouldn't be marked as free
                    self.rf_exp_q.put(rat_state[rl])
                rat_state[rl] = rp
                self.rat_map_q.put({"rl_dst": rl, "rp_dst": rp})
                self.submit_q.put({"rl_dst": rl, "rp_dst": rp})
                # note: overwriting rp with the same value or duplicate rp in rat (except 0) is not possible in
                # complete processor, therefore special checks in retirement and tests for that cases are not included

    def test_rand(self):
        retc = RetirementTestCircuit(self.gen_params)

        def submit_process():
            while not self.submit_q.empty():
                yield from retc.mock_rob_retire.call(self.submit_q.get())

        def free_reg_process():
            while not self.rf_exp_q.empty():
                reg = yield from retc.free_rf_adapter.call()
                self.assertEqual(reg["data"], self.rf_exp_q.get())

        def rat_process():
            while not self.rat_map_q.empty():
                current_map = self.rat_map_q.get()
                # this test waits for next rat pair to be correctly set and will timeout if that assignment fails
                while (yield retc.rat.entries[current_map["rl_dst"]]) != current_map["rp_dst"]:
                    yield

        with self.runSimulation(retc) as sim:
            sim.add_sync_process(submit_process)
            sim.add_sync_process(free_reg_process)
            sim.add_sync_process(rat_process)
