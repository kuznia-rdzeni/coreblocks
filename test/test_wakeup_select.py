from typing import Optional, cast
from amaranth import *
from amaranth.sim import Settle

from collections import deque
from enum import Enum
from inspect import isclass
import random

from coreblocks.genparams import GenParams
from coreblocks.layouts import RSLayouts
from coreblocks.transactions import *
from coreblocks.transactions.lib import Adapter
from coreblocks.wakeup_select import *

from .common import RecordIntDict, TestCaseWithSimulator, TestbenchIO


class WakeupTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.layouts = gen_params.get(RSLayouts)

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        ready_mock = Adapter(o=self.gen_params.rs_entries)
        take_row_mock = Adapter(i=self.gen_params.rs_entries_bits, o=self.layouts.take_out)
        issue_mock = Adapter(i=self.layouts.take_out)
        m.submodules.ready_mock = self.ready_mock = TestbenchIO(ready_mock)
        m.submodules.take_row_mock = self.take_row_mock = TestbenchIO(take_row_mock)
        m.submodules.issue_mock = self.issue_mock = TestbenchIO(issue_mock)
        m.submodules.wakeup_select = WakeupSelect(
            gen_params=self.gen_params, get_ready=ready_mock.iface, take_row=take_row_mock.iface, issue=issue_mock.iface
        )

        dummy = Signal()
        m.d.sync += dummy.eq(1)

        return tm


class TestWakeupSelect(TestCaseWithSimulator):
    def setUp(self):
        self.gen = GenParams("rv32i", rs_entries=16)
        self.m = WakeupTestCircuit(self.gen)
        self.cycles = 50
        self.taken = deque()

        random.seed(42)

    def random_entry(self, layout) -> RecordIntDict:
        result = {}
        for (key, width_or_layout) in layout:
            if isinstance(width_or_layout, int):
                result[key] = random.randrange(width_or_layout)
            elif isclass(width_or_layout) and issubclass(width_or_layout, Enum):
                result[key] = random.choice(list(width_or_layout))
            else:
                result[key] = self.random_entry(width_or_layout)
        return result

    def maybe_insert(self, rs: list[Optional[RecordIntDict]]):
        empty_entries = sum(1 for entry in rs if entry is None)
        if empty_entries > 0 and random.random() < 0.5:
            empty_idx = random.randrange(empty_entries)
            for i, entry in enumerate(rs):
                if entry is None:
                    if empty_idx == 0:
                        rs[i] = self.random_entry(self.m.layouts.take_out)
                        return 1
                    empty_idx -= 1
        return 0

    def process(self):
        inserted_count = 0
        issued_count = 0
        rs: list[Optional[RecordIntDict]] = [None for _ in range(self.m.gen_params.rs_entries)]

        yield from self.m.take_row_mock.enable()
        yield from self.m.issue_mock.enable()
        yield Settle()
        for _ in range(self.cycles):
            inserted_count += self.maybe_insert(rs)
            ready = Cat(entry is not None for entry in rs)

            yield from self.m.ready_mock.call_init({"data": ready})
            if any(entry is not None for entry in rs):
                yield from self.m.ready_mock.enable()
            else:
                yield from self.m.ready_mock.disable()

            yield Settle()

            take_position = yield from self.m.take_row_mock.call_result()
            if take_position is not None:
                take_position = cast(int, take_position["data"])
                entry = rs[take_position]
                self.assertIsNotNone(entry)
                entry = cast(RecordIntDict, entry)  # for type checking

                self.taken.append(entry)
                yield from self.m.take_row_mock.call_init(entry)
                rs[take_position] = None

                yield Settle()

                issued = yield from self.m.issue_mock.call_result()
                if issued is not None:
                    self.assertEqual(issued, self.taken.popleft())
                    issued_count += 1
            yield
        self.assertNotEqual(inserted_count, 0)
        self.assertEqual(inserted_count, issued_count)

    def test(self):
        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.process)
