import random
from operator import and_
from functools import reduce

from amaranth import *
from transactron.lib import FIFO, AdapterTrans, Adapter, ManyToOneConnectTrans
from coreblocks.backend.annoucement import ResultAnnouncement
from coreblocks.interface.layouts import *
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.testing import TestCaseWithSimulator, TestbenchIO, TestbenchContext


class BackendTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, fu_count: int = 1):
        self.gen_params = gen_params

        self.fu_count = fu_count
        self.fu_fifo_ins = []

    def elaborate(self, platform):
        m = Module()

        self.lay_result = self.gen_params.get(FuncUnitLayouts).accept
        self.lay_rob_mark_done = self.gen_params.get(ROBLayouts).mark_done_layout
        self.lay_rs_write = self.gen_params.get(
            RSLayouts, rs_entries_bits=self.gen_params.max_rs_entries_bits
        ).rs.update_in
        self.lay_rf_write = self.gen_params.get(RFLayouts).rf_write

        # Initialize for each FU an FIFO which will be a stub for that FU
        fu_fifos = []
        get_results = []
        for i in range(self.fu_count):
            fifo = FIFO(self.lay_result, 16)
            fu_fifos.append(fifo)
            get_results.append(fifo.read)
            m.submodules[f"fu_fifo_{i}"] = fifo

            fifo_in = TestbenchIO(AdapterTrans(fifo.write))
            m.submodules[f"fu_fifo_{i}_in"] = fifo_in
            self.fu_fifo_ins.append(fifo_in)

        # Create FUArbiter, which will serialize results from different FU's
        serialized_results_fifo = FIFO(self.lay_result, 16)
        m.submodules.serialized_results_fifo = serialized_results_fifo
        m.submodules.fu_arbitration = ManyToOneConnectTrans(
            get_results=get_results, put_result=serialized_results_fifo.write
        )

        # Create stubs for interfaces used by result announcement
        self.rs_announce_val_tbio = TestbenchIO(Adapter.create(i=self.lay_rs_write, o=self.lay_rs_write))
        m.submodules.rs_announce_val_tbio = self.rs_announce_val_tbio
        self.rf_announce_val_tbio = TestbenchIO(Adapter.create(i=self.lay_rf_write, o=self.lay_rf_write))
        m.submodules.rf_announce_val_tbio = self.rf_announce_val_tbio
        self.rob_mark_done_tbio = TestbenchIO(Adapter.create(i=self.lay_rob_mark_done, o=self.lay_rob_mark_done))
        m.submodules.rob_mark_done_tbio = self.rob_mark_done_tbio

        # Create result announcement
        m.submodules.result_announcement = ResultAnnouncement(
            gen_params=self.gen_params,
            get_result=serialized_results_fifo.read,
            rob_mark_done=self.rob_mark_done_tbio.adapter.iface,
            rs_update=self.rs_announce_val_tbio.adapter.iface,
            rf_write=self.rf_announce_val_tbio.adapter.iface,
        )

        return m


class TestBackend(TestCaseWithSimulator):
    def initialize(self):
        self.gen_params = GenParams(test_core_config)
        self.m = BackendTestCircuit(self.gen_params, self.fu_count)
        random.seed(14)
        self.max_wait = 3

        self.fu_inputs = []
        # Create list with info if we processed all results from FU
        self.producer_end = [False for i in range(self.fu_count)]
        self.expected_output = {}

        # Prepare random results from FU
        for i in range(self.fu_count):
            inputs = []
            input_size = random.randint(90, 110)
            for j in range(input_size):
                t = (
                    random.randint(0, 2**self.gen_params.rob_entries_bits),
                    random.randint(0, 2**self.gen_params.isa.xlen),
                    random.randint(0, 2**self.gen_params.phys_regs_bits),
                )
                inputs.append(t)
                if t in self.expected_output:
                    self.expected_output[t] += 1
                else:
                    self.expected_output[t] = 1
            self.fu_inputs.append(inputs)

    def generate_producer(self, i: int):
        """
        This is an helper function, which generates a producer process,
        which will simulate an FU. Producer will insert in random intervals new
        results to its output FIFO. This records will be next serialized by FUArbiter.
        """

        async def producer(sim: TestbenchContext):
            inputs = self.fu_inputs[i]
            for rob_id, result, rp_dst in inputs:
                io: TestbenchIO = self.m.fu_fifo_ins[i]
                io.call_init(sim, rob_id=rob_id, result=result, rp_dst=rp_dst)
                await self.random_wait(sim, self.max_wait)
            self.producer_end[i] = True

        return producer

    async def consumer(self, sim: TestbenchContext):
        # TODO: this test doesn't do anything, fix it!
        self.m.rs_announce_val_tbio.enable(sim)
        self.m.rob_mark_done_tbio.enable(sim)
        while reduce(and_, self.producer_end, True):
            # All 3 methods (in RF, RS and ROB) need to be enabled for the result
            # announcement transaction to take place. We want to have at least one
            # method disabled most of the time, so that the transaction is performed
            # only when we enable it inside the loop. Otherwise the transaction could
            # get executed at any time, particularly when we wouldn't be monitoring it
            self.m.rf_announce_val_tbio.enable(sim)

            rf_result = self.m.rf_announce_val_tbio.get_outputs(sim)
            rs_result = self.m.rs_announce_val_tbio.get_outputs(sim)
            rob_result = self.m.rob_mark_done_tbio.get_outputs(sim)

            self.m.rf_announce_val_tbio.disable(sim)

            assert rf_result is not None
            assert rs_result is not None
            assert rob_result is not None

            assert rf_result["reg_val"] == rs_result["value"]
            assert rf_result["reg_id"] == rs_result["reg_id"]

            t = (rob_result["rob_id"], rf_result["reg_val"], rf_result["reg_id"])
            assert t in self.expected_output
            if self.expected_output[t] == 1:
                del self.expected_output[t]
            else:
                self.expected_output[t] -= 1
            await self.random_wait(sim, self.max_wait)

    def test_one_out(self):
        self.fu_count = 1
        self.initialize()
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.consumer)
            for i in range(self.fu_count):
                sim.add_testbench(self.generate_producer(i))

    def test_many_out(self):
        self.fu_count = 4
        self.initialize()
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.consumer)
            for i in range(self.fu_count):
                sim.add_testbench(self.generate_producer(i))
