from amaranth import *
from coreblocks.utils.fifo import BasicFifo
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from test.common import TestCaseWithSimulator, TestbenchIO
from collections import deque
import random


class BasicFifoTestCircuit(Elaboratable):
    def __init__(self, init):
        self.init = init

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.fifo = self.fifo = BasicFifo(layout=8, depth=5, init=self.init)

        m.submodules.fifo_read = self.fifo_read = TestbenchIO(AdapterTrans(self.fifo.read))
        m.submodules.fifo_write = self.fifo_write = TestbenchIO(AdapterTrans(self.fifo.write))
        m.submodules.fifo_clear = self.fifo_clear = TestbenchIO(AdapterTrans(self.fifo.clear))

        return tm


class TestBasicFifo(TestCaseWithSimulator):
    def test_randomized(self):
        init_values = [1, 2, 4]

        fifoc = BasicFifoTestCircuit(init_values)
        expq = deque(reversed(init_values))  # first expected element is at the start of init_list

        cycles = 256
        random.seed(42)

        self.done = False

        def source():
            for _ in range(cycles):
                if random.randint(0, 1):
                    yield  # random delay

                v = random.randint(0, (2**fifoc.fifo.width) - 1)
                yield from fifoc.fifo_write.call({"data": v})
                expq.appendleft(v)

                if random.random() < 0.005:
                    yield from fifoc.fifo_clear.call()
                    expq.clear()

            self.done = True

        def target():
            while not self.done or expq:
                if random.randint(0, 1):
                    yield

                yield from fifoc.fifo_read.call_init()
                yield

                v = yield from fifoc.fifo_read.call_result()
                if v is not None:
                    self.assertEqual(v["data"], expq.pop())

                yield from fifoc.fifo_read.disable()

        with self.runSimulation(fifoc) as sim:
            sim.add_sync_process(source)
            sim.add_sync_process(target)
