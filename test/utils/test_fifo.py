from amaranth import *

from coreblocks.utils.fifo import BasicFifo
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from test.common import TestCaseWithSimulator, TestbenchIO, data_layout
from collections import deque
from parameterized import parameterized_class
import random


class BasicFifoTestCircuit(Elaboratable):
    def __init__(self, depth):
        self.depth = depth

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.fifo = self.fifo = BasicFifo(layout=data_layout(8), depth=self.depth)

        m.submodules.fifo_read = self.fifo_read = TestbenchIO(AdapterTrans(self.fifo.read))
        m.submodules.fifo_write = self.fifo_write = TestbenchIO(AdapterTrans(self.fifo.write))
        m.submodules.fifo_clear = self.fifo_clear = TestbenchIO(AdapterTrans(self.fifo.clear))

        return tm


@parameterized_class(
    ("name", "depth"),
    [
        ("notpower", 5, 0),
        ("power", 4, 0),
    ],
)
class TestBasicFifo(TestCaseWithSimulator):
    depth: int

    def test_randomized(self):
        fifoc = BasicFifoTestCircuit(depth=self.depth)
        expq = deque()  # first expected element is at the start of init_list

        cycles = 256
        random.seed(42)

        self.done = False

        def source():
            for _ in range(cycles):
                if random.randint(0, 1):
                    yield  # random delay

                v = random.randint(0, (2**fifoc.fifo.width) - 1)
                yield from fifoc.fifo_write.call(data=v)
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

        with self.run_simulation(fifoc) as sim:
            sim.add_sync_process(source)
            sim.add_sync_process(target)
