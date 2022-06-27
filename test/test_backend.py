import random
from operator import and_
from functools import reduce

from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator, Settle
from coreblocks.transactions import TransactionModule, TransactionContext
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans, Adapter
from coreblocks.backend import FUArbitration, ResultAnnouncement
from coreblocks.layouts import *
from coreblocks.genparams import GenParams
from .common import RecordIntDict, TestCaseWithSimulator, TestGen, TestbenchIO


class BackendTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams, fu_count: int = 1):
        self.gen = gen

        self.fu_count = fu_count

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.lay_result = self.gen.get(FuncUnitLayouts).accept
        self.lay_rob_mark_done = self.gen.get(ROBLayouts).id_layout
        self.lay_rs_write = self.gen.get(RSLayouts).rs_announce_val
        self.lay_rf_write = self.gen.get(RFLayouts).rf_write

        with tm.transactionContext():
            # Initialize for each FU an FIFO which will be a stub for that FU
            fu_fifos = []
            get_results = []
            for i in range(self.fu_count):
                fifo = FIFO(self.lay_result, 16)
                fu_fifos.append(fifo)
                get_results.append(fifo.read)
                setattr(m.submodules, f"fu_fifo_{i}", fifo)

                fifo_in = TestbenchIO(AdapterTrans(fifo.write))
                setattr(m.submodules, f"fu_fifo_{i}_in", fifo_in)
                setattr(self, f"fu_fifo_{i}_in", fifo_in)

            # Create FUArbiter, which will serialize results from different FU's
            serialized_results_fifo = FIFO(self.lay_result, 16)
            m.submodules.serialized_results_fifo = serialized_results_fifo
            m.submodules.fu_arbitration = FUArbitration(
                gen=self.gen, get_results=get_results, put_result=serialized_results_fifo.write
            )

            # Create stubs for interfaces used by result announcement
            self.rs_announce_val_tbio = TestbenchIO(Adapter(i=self.lay_rs_write, o=self.lay_rs_write))
            m.submodules.rs_announce_val_tbio = self.rs_announce_val_tbio
            self.rf_announce_val_tbio = TestbenchIO(Adapter(i=self.lay_rf_write, o=self.lay_rf_write))
            m.submodules.rf_announce_val_tbio = self.rf_announce_val_tbio
            self.rob_mark_done_tbio = TestbenchIO(Adapter(i=self.lay_rob_mark_done, o=self.lay_rob_mark_done))
            m.submodules.rob_mark_done_tbio = self.rob_mark_done_tbio

            # Create result announcement
            m.submodules.result_announcement = ResultAnnouncement(
                gen=self.gen,
                get_result=serialized_results_fifo.read,
                rob_mark_done=self.rob_mark_done_tbio.adapter.iface,
                rs_write_val=self.rs_announce_val_tbio.adapter.iface,
                rf_write_val=self.rf_announce_val_tbio.adapter.iface,
            )

        return tm


class TestBackend(TestCaseWithSimulator):
    def initialize(self):
        gen = GenParams("rv32i")
        self.m = BackendTestCircuit(gen, self.fu_count)
        random.seed(14)

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
                    random.randint(0, 2**gen.rob_entries_bits),
                    random.randint(0, 2**gen.isa.xlen),
                    random.randint(0, 2**gen.phys_regs_bits),
                )
                inputs.append(t)
                if t in self.expected_output:
                    self.expected_output[t] += 1
                else:
                    self.expected_output[t] = 1
            self.fu_inputs.append(inputs)

    def random_wait(self):
        for i in range(random.randint(0, 3)):
            yield

    def generate_producer(self, i: int):
        """
        This is an helper function, which generates a producer process,
        which will simulate an FU. Producer will insert in random intervals new
        results to its output FIFO. This records will be next serialized by FUArbiter.
        """

        def producer():
            inputs = self.fu_inputs[i]
            while inputs:
                input = inputs.pop()
                input_dict = {"rob_id": input[0], "result": input[1], "rp_dst": input[2]}
                yield from getattr(self.m, f"fu_fifo_{i}_in").call_init(input_dict)
                yield from self.random_wait()
            self.producer_end[i] = True

        return producer

    def consumer(self):
        yield from self.m.rs_announce_val_tbio.enable()
        yield from self.m.rob_mark_done_tbio.enable()
        while reduce(and_, self.producer_end, True):
            rf_result = yield from self.m.rf_announce_val_tbio.call_do()
            rs_result = yield from self.m.rs_announce_val_tbio.call_result()
            rob_result = yield from self.m.rob_mark_done_tbio.call_result()

            self.assertIsNotNone(rf_result)
            self.assertIsNotNone(rs_result)
            self.assertIsNotNone(rob_result)

            if rf_result is None or rs_result is None or rob_result is None:
                continue

            self.assertEqual(rf_result["reg_val"], rs_result["value"])
            self.assertEqual(rf_result["reg_id"], rs_result["reg_id"])

            t = (rob_result["rob_id"], rf_result["reg_val"], rf_result["reg_id"])
            self.assertIn(t, self.expected_output)
            if self.expected_output[t] == 1:
                del self.expected_output[t]
            else:
                self.expected_output[t] -= 1
            yield from self.random_wait()

    def test_one_out(self):
        self.fu_count = 1
        self.initialize()
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.fu_count):
                sim.add_sync_process(self.generate_producer(i))

    def test_many_out(self):
        self.fu_count = 4
        self.initialize()
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.fu_count):
                sim.add_sync_process(self.generate_producer(i))
