import random
from operator import and_
from functools import reduce

from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator, Settle
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans, Adapter, ManyToOneConnectTrans
from coreblocks._typing import LayoutLike
from .common import RecordIntDict, TestCaseWithSimulator, TestGen, TestbenchIO
from coreblocks.transactions import TransactionModule, TransactionContext


class ManyToOneConnectTransTestCircuit(Elaboratable):
    def __init__(self, count: int, lay: LayoutLike):
        self.count = count
        self.lay = lay

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        # dummy signal
        s = Signal()
        m.d.sync += s.eq(1)

        with tm.transactionContext():
            get_results = []
            for i in range(self.count):
                input = TestbenchIO(Adapter(i=self.lay, o=self.lay))
                get_results.append(input.adapter.iface)
                setattr(m.submodules, f"input_{i}", input)
                setattr(self, f"input_{i}", input)

            # Create ManyToOneConnectTrans, which will serialize results from different inputs
            output = TestbenchIO(Adapter(i=self.lay))
            m.submodules.output = output
            self.output = output
            m.submodules.fu_arbitration = ManyToOneConnectTrans(
                get_results=get_results, put_result=output.adapter.iface
            )

        return tm


class TestManyToOneConnectTrans(TestCaseWithSimulator):
    def initialize(self):
        f1_size = 14
        f2_size = 3
        self.lay = [("field1", f1_size), ("field2", f2_size)]

        self.m = ManyToOneConnectTransTestCircuit(self.count, self.lay)
        random.seed(14)

        self.inputs = []
        # Create list with info if we processed all data from inputs
        self.producer_end = [False for i in range(self.count)]
        self.expected_output = {}

        # Prepare random results for inputs
        for i in range(self.count):
            data = []
            input_size = random.randint(20, 30)
            for j in range(input_size):
                t = (
                    random.randint(0, 2**f1_size),
                    random.randint(0, 2**f2_size),
                )
                data.append(t)
                if t in self.expected_output:
                    self.expected_output[t] += 1
                else:
                    self.expected_output[t] = 1
            self.inputs.append(data)

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
            inputs = self.inputs[i]
            for field1, field2 in inputs:
                input_dict = {"field1": field1, "field2": field2}
                yield from getattr(self.m, f"input_{i}").call_init(input_dict)
                yield from self.random_wait()
            self.producer_end[i] = True

        return producer

    def consumer(self):
        while reduce(and_, self.producer_end, True):
            result = yield from self.m.output.call_do()

            self.assertIsNotNone(result)

            if result is None:
                continue

            t = (result["field1"], result["field2"])
            self.assertIn(t, self.expected_output)
            if self.expected_output[t] == 1:
                del self.expected_output[t]
            else:
                self.expected_output[t] -= 1
            yield from self.random_wait()

    def test_one_out(self):
        self.count = 1
        self.initialize()
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.count):
                sim.add_sync_process(self.generate_producer(i))

    def test_many_out(self):
        self.count = 4
        self.initialize()
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.consumer)
            for i in range(self.count):
                sim.add_sync_process(self.generate_producer(i))
