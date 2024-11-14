from amaranth import *

from transactron.lib import AdapterTrans, BasicFifo

from transactron.testing import TestCaseWithSimulator, TestbenchIO, data_layout, TestbenchContext
from collections import deque
from parameterized import parameterized_class
import random


class BasicFifoTestCircuit(Elaboratable):
    def __init__(self, depth):
        self.depth = depth

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = self.fifo = BasicFifo(layout=data_layout(8), depth=self.depth)

        m.submodules.fifo_read = self.fifo_read = TestbenchIO(AdapterTrans(self.fifo.read))
        m.submodules.fifo_write = self.fifo_write = TestbenchIO(AdapterTrans(self.fifo.write))
        m.submodules.fifo_clear = self.fifo_clear = TestbenchIO(AdapterTrans(self.fifo.clear))

        return m


@parameterized_class(
    ("name", "depth"),
    [
        ("notpower", 5),
        ("power", 4),
    ],
)
class TestBasicFifo(TestCaseWithSimulator):
    depth: int

    def test_randomized(self):
        fifoc = BasicFifoTestCircuit(depth=self.depth)
        expq = deque()

        cycles = 256
        random.seed(42)

        self.done = False

        async def source(sim: TestbenchContext):
            for _ in range(cycles):
                await self.random_wait_geom(sim, 0.5)

                v = random.randint(0, (2**fifoc.fifo.width) - 1)
                expq.appendleft(v)
                await fifoc.fifo_write.call(sim, data=v)

                if random.random() < 0.005:
                    await fifoc.fifo_clear.call(sim)
                    await sim.delay(1e-9)
                    expq.clear()

            self.done = True

        async def target(sim: TestbenchContext):
            while not self.done or expq:
                await self.random_wait_geom(sim, 0.5)

                v = await fifoc.fifo_read.call_try(sim)

                if v is not None:
                    assert v.data == expq.pop()

        with self.run_simulation(fifoc) as sim:
            sim.add_testbench(source)
            sim.add_testbench(target)
