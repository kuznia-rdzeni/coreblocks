from amaranth import *
from amaranth.sim import Settle

from collections import deque
import random

from coreblocks.genparams import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import Adapter, AdapterTrans
from coreblocks.wakeup_select import *

from .common import TestCaseWithSimulator, TestbenchIO


class WakeupTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.layouts = gen_params.get(RSLayouts)

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            ready_mock = Adapter(o=self.layouts.rs_entries_bits)
            take_row_mock = Adapter(i=self.layouts.rs_entries_bits, o=self.layouts.rs_out)
            issue_mock = Adapter(i=self.layouts.rs_out)
            m.submodules.ready_mock = self.ready_mock = TestbenchIO(ready_mock)
            m.submodules.take_row_mock = self.take_row_mock = TestbenchIO(take_row_mock)
            m.submodules.issue_mock = self.issue_mock = TestbenchIO(issue_mock)
            m.submodules.wakeup_select = WakeupSelect(
                get_ready=ready_mock.iface, take_row=take_row_mock.iface, issue=issue_mock.iface
            )

            dummy = Signal()
            m.d.sync += dummy.eq(1)

        return tm


class TestWakeupSelect(TestCaseWithSimulator):
    def setUp(self):
        self.gen = GenParams("rv32i")
        self.m = WakeupTestCircuit(self.gen)
        self.cycles = 40
        self.taken = deque()

        random.seed(42)

    def random_entry(self):
        return {key: random.randrange(width) for (key, width) in self.m.layouts.rs_out}

    def maybe_insert(self, rs):
        empty_entries = sum(1 for entry in rs if entry is None)
        if empty_entries > 0 and random.random() < 0.5:
            empty_idx = random.randrange(empty_entries)
            for i, entry in enumerate(rs):
                if entry is None:
                    if empty_idx == 0:
                        rs[i] = self.random_entry()
                        break
                    empty_idx -= 1

    def rs_process(self):
        rs_entries = 1 << self.m.layouts.rs_entries_bits
        rs = [None for _ in range(rs_entries)]
        yield from self.m.take_row_mock.enable()
        yield from self.m.issue_mock.enable()
        yield Settle()
        for _ in range(self.cycles):
            self.maybe_insert(rs)

            ready = Cat(entry is not None for entry in rs)
            yield from self.m.ready_mock.call_init({"data": ready})
            if any(entry is not None for entry in rs):
                yield from self.m.ready_mock.enable()
            else:
                yield from self.m.ready_mock.disable()
            print('rdy_bits', (yield self.m.ready_mock.adapter.iface.data_in['data']))
            #yield self.m.ready_mock.adapter.iface.data_in['data'].eq(1)
            yield Settle()
            #print((yield self.m.ready_mock.adapter.iface.data_in['data']))
            print('rdy', ready)
            print('tr', (yield self.m.take_row_mock.adapter.iface.data_in['data']))
            take_position = yield from self.m.take_row_mock.call_result()
            if take_position is not None:
                print('tp', take_position)
                self.taken.append(rs[take_position])
                yield from self.m.take_row_mock.call_init(rs[take_position])
                rs[take_position] = None
                if all(entry is None for entry in rs):
                    yield from self.m.ready_mock.disable()
            yield

    def fu_process(self):
        yield from self.m.issue_mock.enable()
        for _ in range(self.cycles):
            entry = yield from self.m.issue_mock.call_result()
            if entry is not None:
                assert entry == self.taken.popleft()
            yield

    def test(self):
        with self.runSimulation(self.m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.rs_process)
            sim.add_sync_process(self.fu_process)
