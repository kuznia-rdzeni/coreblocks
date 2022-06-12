import random
from operator import or_
from functools import reduce

from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator, Settle
from coreblocks.transactions import TransactionModule, TransactionContext
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans, Adapter
from coreblocks.backend import FUArbitration, ResultAnnouncemet
from coreblocks.layouts import SchedulerLayouts
from coreblocks.genparams import GenParams
from .common import RecordIntDict, TestCaseWithSimulator, TestGen, TestbenchIO


class BackendTestCircuit(Elaboratable):
    def __init__(self, gen: GenParams, fu_count: int = 1):
        self.gen = gen

        self.fu_count = fu_count

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        self.lay_result = gen.get(FuncUnitLayouts).accept
        self.lay_rob_mark_done = gen.get(ROBLayouts).id_layout
        self.lay_rs_write = gen.get(RSLayouts).rs_announce_val
        self.lay_rf_write = gen.get(RFLayouts).rf_write

        with tm.transactionContext():
            fu_fifos = []
            get_results = []
            for i in range(self.fu_count):
                fifo = FIFO(self.lay_result)
                fu_fifos.append(fifo)
                get_results.append(fifo.read)
                setattr(m.submodules, f"fu_fifo_{i}", fifo)

                fifo_in = TestbenchIO(AdapterTrans(fifo.write))
                setattr(m.submodules, f"fu_fifo_{i}_in", fifo_in)
                setattr(self, f"fu_fifo_{i}_in", fifo_in)

            serialized_results_fifo = FIFO(self.lay_result)
            fu_arbitration = FUArbitration(gen, get_results, serialized_results_fifo.write)

            self.rs_announce_val_tbio = TestbenchIO(Adapter(i=self.lay_rs_write, o=self.lay_rs_write))
            m.submodules.rs_announce_val_tbio = self.rs_announce_val_tbio
            self.rf_write_val_tbio = TestbenchIO(Adapter(i=self.lay_rf_write, o=self.lay_rf_write))
            m.submodules.rf_announce_val_tbio = self.rf_announce_val_tbio
            self.rob_mark_done_tbio = TestbenchIO(Adapter(i=self.lay_rob_mark_done, o=self.lay_rob_mark_done))
            m.submodules.rob_mark_done_tbio = self.rob_mark_done_tbio

            result_announcement = ResultAnnouncemet(
                gen,
                serialized_results_fifo.read,
                rob_mark_done_tbio.adapter.iface,
                rs_announce_val_tbio.adapter.iface,
                rf_write_val_tbio.adapter.iface,
            )

        return tm


class TestBackend(TestCaseWithSimulator):
    def setUp(self):
        gen = GenParams("rv32i")
        fu_count = 1
        self.m = BackendTestCircuit(gen, fu_count)
        random.seed(14)

        self.fu_inputs = []
        self.producer_end = [False for i in range(fu_count)]
        self.expected_output = {}
        for i in range(fu_count):
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

    def random_wait():
        for i in range(random.randint(0, 3)):
            yield

    def generate_producer(self, i: int):
        def producer():
            inputs = self.fu_inputs[i]
            while inputs:
                input = inputs.pop()
                yield from getattr(self, f"fu_fifo_{i}_in")
                yield from random_wait()
            self.producer_end[i] = True

        return producer

    def consumer():
        yield from self.m.rs_write_val_tbio.enable()
        yield from self.m.rob_mark_done_tbio.enable()
        while reduce(and_, self.producer_end, True):
            rf_result = yield from self.m.rf_write_val_tbio.call_do()
            rs_result = yield from self.m.rs_write_val_tbio.call_result()
            rob_result = yield from self.m.rob_mark_done_tbio.call_result()

            self.assertIsNotNone(rf_result)
            self.assertIsNotNone(rs_result)
            self.assertIsNotNone(rob_result)

            self.assertEqual(rf_result.reg_val, rs_result.value)
            self.assertEqual(rf_result.reg_id, rs_result.reg_id)

            t = (rob_result.rob_id, rf_result.reg_val, rf_result.reg_id)
            self.assertIn(t, self.expected_output)
            if self.expected_output[t] == 1:
                del self.expected_output[i]
            else:
                self.expected_output -= 1
            yield from random_wait()

        #TODO Dokończyć pisanie testu, dodać procesy, zegar itp.
