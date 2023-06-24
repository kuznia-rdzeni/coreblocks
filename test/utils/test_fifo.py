from amaranth import *
from amaranth.sim import Settle, Passive, Active

from coreblocks.utils.fifo import BasicFifo, MultiportFifo
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from coreblocks.utils._typing import LayoutLike

from test.common import TestCaseWithSimulator, TestbenchIO, data_layout, SimpleTestCircuit
from collections import deque
from parameterized import parameterized_class
import random
from typing import Callable


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
    fifo_constructor: Callable[[LayoutLike, int, int, int], Elaboratable]

    def test_randomized(self):
        layout = data_layout(8)
        width = len(Record(layout))
        fifoc = SimpleTestCircuit( self.fifo_constructor(layout, self.depth, self.port_count, self.fifo_count))
        writed: list[tuple[int, int, int]] = []  # (cycle_id, port_id, value)
        readed = []
        clears = []

        dones = [False for _ in range(self.port_count)]

        packet_counter = 0
        cycles = 100
        random.seed(42)

        def source_generator(port_id: int):
            def source():
                nonlocal packet_counter
                cycle = 0
                for _ in range(cycles):
                    cycle += 1
                    if random.randint(0, 1):
                        cycle += 1
                        yield  # random delay

                    if port_id == 0 and random.random() < 0.05:
                        if (yield from fifoc.clear.call_try()) is None:
                            assert "Clearing failed"
                        clears.append(cycle)
                        cycle += 1
                        packet_counter = 0

                    v = random.randrange(2**width)
                    yield Settle()
                    while (yield from fifoc.write_methods[port_id].call_try(data=v)) is None:
                        cycle += 1
                    writed.append((cycle, port_id, v))
                    packet_counter += 1
                dones[port_id] = True

            return source

        def target_generator(port_id: int):
            def target():
                nonlocal packet_counter
                yield Passive()
                cycle = 0
                while True:
                    cycle += 1
                    if random.randint(0, 1):
                        cycle += 1
                        yield

                    v = yield from fifoc.read_methods[port_id].call_try()
                    if v is not None:
                        readed.append((cycle, port_id, v["data"]))
                        packet_counter-=1
                    if packet_counter==0:
                        yield Passive()
                    else:
                        yield Active()

            return target

        def checker():
            while not all(dones) or packet_counter>0:
                yield
            readed.sort()
            writed.sort()
            INF_INT = 1000000000
            clears.append(INF_INT)

            write_it = 0
            clear_it = 0
            # check property:
            # If value `val` was inserted in `write_cycle` and readed in `read_cycle` then
            # every value `x` inserted in `x_write_cycle` < `write_cycle` should be read
            # in `x_read_cycle` <= `read_cycle`.
            def find_read_idx(cycle, val):
                for i, (rc, _, vr) in enumerate(readed):
                    if rc>clears[0]:
                        return None
                    if vr == val and rc>cycle:
                        return i
                raise RuntimeError()
            paired = {}
            first_cleared = INF_INT
            for idx, entry  in enumerate(writed):
                (write_cycle, port, val) = entry
                while write_cycle>clears[0]:
                    clears.pop(0)
                    first_cleared = INF_INT
                if write_cycle > first_cleared:
                    continue
                earlier_writes = list(filter(lambda x: x[0]<write_cycle, writed))
                read_idx = find_read_idx(write_cycle, val)
                if read_idx is not None:
                    read_entry = readed[read_idx]
                    readed.pop(read_idx)
                    paired[entry] = read_entry
                    for x_entry in earlier_writes:
                        (x_write_cycle, x_port, x) = x_entry
                        try:
                            rx_entry = paired[x_entry]
                            self.assertLessEqual(rx_entry[0], read_entry[0])
                        except KeyError:
                            pass
                else:
                    first_cleared = write_cycle
            self.assertEqual(0, len(readed))

        with self.run_simulation(fifoc, 4000) as sim:
            sim.add_sync_process(checker)
            for i in range(self.port_count):
                sim.add_sync_process(source_generator(i))
                sim.add_sync_process(target_generator(i))
