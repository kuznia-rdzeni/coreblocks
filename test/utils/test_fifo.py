from amaranth import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from test.common import TestCaseWithSimulator, TestbenchIO
from collections import deque
import random


class BasicFifoTestCircuit(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.fifo = self.fifo = BasicFifo(8, 10)

        m.submodules.fifo_read = self.fifo_read = TestbenchIO(AdapterTrans(self.fifo.read))
        m.submodules.fifo_write = self.fifo_write = TestbenchIO(AdapterTrans(self.fifo.write))

        return tm


class TestBasicFifo(TestCaseWithSimulator):
    def test_randomized(self):
        fifoc = BasicFifoTestCircuit()
        expq = deque()

        cycles = 256
        random.seed(42)

        def source():
            for _ in range(cycles):
                if random.randint(0, 1):
                    yield  # random delay

                v = random.randint(0, (2**fifoc.fifo.width) - 1)
                print("put", v)
                yield from fifoc.fifo_write.call({"data": v})
                expq.appendleft(v)

        def target():
            for _ in range(cycles):
                if random.randint(0, 1):
                    yield

                v = yield from fifoc.fifo_read.call()
                print("take", v)
                self.assertEqual(v["data"], expq.pop())

        with self.runSimulation(fifoc) as sim:
            sim.add_sync_process(source)
            sim.add_sync_process(target)
