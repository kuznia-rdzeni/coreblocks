from amaranth import *
from amaranth.sim import Settle, Passive

from coreblocks.utils.fifo import BasicFifo, MultiportFifo
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from coreblocks.utils._typing import LayoutLike

from test.common import TestCaseWithSimulator, TestbenchIO, data_layout
from collections import deque
from parameterized import parameterized_class
import random
from typing import Callable


# class FifoTestCircuit(Elaboratable):
#    def __init__(self, depth, init, fifo_constructor):
#        self.depth = depth
#        self.init = init
#        self.fifo_constructor = fifo_constructor
#
#    def elaborate(self, platform):
#        m = Module()
#        tm = TransactionModule(m)
#
#        m.submodules.fifo = self.fifo = self.fifo_constructor(layout=data_layout(8), depth=self.depth, init=self.init)
#
#        m.submodules.fifo_read = self.fifo_read = TestbenchIO(AdapterTrans(self.fifo.get_read()))
#        m.submodules.fifo_write = self.fifo_write = TestbenchIO(AdapterTrans(self.fifo.get_write()))
#        m.submodules.fifo_clear = self.fifo_clear = TestbenchIO(AdapterTrans(self.fifo.clear))
#
#        return tm


class FifoTestCircuit(Elaboratable):
    def __init__(self, depth, port_count, fifo_count, fifo_constructor):
        self.depth = depth
        self.port_count = port_count
        self.fifo_count = fifo_count
        self.fifo_constructor = fifo_constructor

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = self.fifo = self.fifo_constructor(
            layout=data_layout(8), depth=self.depth, fifo_count=self.fifo_count, port_count=self.port_count
        )

        self.fifo_reads = []
        self.fifo_writes = []
        for i in range(self.port_count):
            self.fifo_reads.append(TestbenchIO(AdapterTrans(self.fifo.get_read())))
            self.fifo_writes.append(TestbenchIO(AdapterTrans(self.fifo.get_write())))
            setattr(m.submodules, f"fifo_read_{i}", self.fifo_reads[i])
            setattr(m.submodules, f"fifo_write_{i}", self.fifo_writes[i])
        m.submodules.fifo_clear = self.fifo_clear = TestbenchIO(AdapterTrans(self.fifo.clear))

        return m


params_dinit = [
    ("notpower", 12),
    ("power", 8),
]

params_c = [
    (
        "basic",
        lambda self, layout, depth, port_count, fifo_count: BasicFifo(layout=layout, depth=depth),
    ),
    (
        "multi",
        lambda self, layout, depth, port_count, fifo_count: MultiportFifo(
            layout=layout, depth=depth, port_count=port_count, fifo_count=fifo_count
        ),
    ),
]


@parameterized_class(
    ("name", "depth", "port_count", "fifo_count", "name_constr", "fifo_constructor"),
    [dinit + (1, 1) + constr for dinit in params_dinit for constr in params_c]
    + [dinit + (4, 4) + params_c[1] for dinit in params_dinit],
)
class TestBasicFifo(TestCaseWithSimulator):
    depth: int
    port_count: int
    fifo_count: int
    fifo_constructor: Callable[[LayoutLike, int, int], Elaboratable]

    def test_randomized(self):
        fifoc = FifoTestCircuit(
            depth=self.depth,
            port_count=self.port_count,
            fifo_count=self.fifo_count,
            fifo_constructor=self.fifo_constructor,
        )
        writed: list[tuple[int, int, int]] = []  # (cycle_id, port_id, value)
        readed = []
        clears = []

        dones = [False for _ in range(self.port_count)]

        cycles = 256
        random.seed(44)

        def source_generator(port_id: int):
            def source():
                cycle = 0
                for _ in range(cycles):
                    cycle += 1
                    if random.randint(0, 1):
                        cycle += 1
                        yield  # random delay

                    if port_id == 0 and random.random() < 0.005:
                        if (yield from fifoc.fifo_clear.call_try()) is None:
                            assert "Clearing failed"
                        clears.append((cycle, port_id))
                        cycle += 1

                    v = random.randrange(2**fifoc.fifo.width)
                    yield Settle()
                    while (yield from fifoc.fifo_writes[port_id].call_try(data=v)) is None:
                        cycle += 1
                    writed.append((cycle, port_id, v))
                dones[port_id] = True

            return source

        def target_generator(port_id: int):
            def target():
                yield Passive()
                cycle = 0
                while True:
                    cycle += 1
                    if random.randint(0, 1):
                        cycle += 1
                        yield

                    v = yield from fifoc.fifo_reads[port_id].call_try()
                    if v is not None:
                        readed.append((cycle, port_id, v["data"]))

            return target

        def checker():
            while not all(dones):
                yield
            readed.sort()
            writed.sort()
            INF_INT = 1000000000
            clears.append((INF_INT, -1))
            #            print(readed)
            #            print(writed)

            write_it = 0
            clear_it = 0
            for i, (cycle, port_id, val) in enumerate(readed):
                while cycle > clears[clear_it][0]:
                    while writed[write_it][0] < clears[clear_it][0]:
                        # print(writed[write_it],clears[clear_it])
                        write_it += 1
                    if write_it >= len(writed):
                        break
                    clear_it += 1
                # print(clears)
                # print("odczytana:",val, "zapisana:",writed[write_it], "cykl_odczytu:", cycle, "port", port_id)
                self.assertEqual(val, writed[write_it][2])
                write_it += 1

        with self.run_simulation(fifoc) as sim:
            sim.add_sync_process(checker)
            #            sim.add_sync_process(source_generator(0))
            #            sim.add_sync_process(source_generator(1))
            #            sim.add_sync_process(target_generator(0))
            for i in range(self.port_count):
                sim.add_sync_process(source_generator(i))
                sim.add_sync_process(target_generator(i))
