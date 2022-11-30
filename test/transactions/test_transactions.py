from unittest.case import TestCase
from amaranth import *
from amaranth.sim import *

import random

from collections import deque
from typing import Iterable, Callable
from parameterized import parameterized, parameterized_class

from ..common import TestCaseWithSimulator, TestbenchIO

from coreblocks.transactions import *
from coreblocks.transactions.lib import Adapter, AdapterTrans
from coreblocks.transactions._utils import Scheduler

from coreblocks.transactions.core import (
    TransactionScheduler,
    trivial_roundrobin_cc_scheduler,
    eager_deterministic_cc_scheduler,
)


class TestNames(TestCase):
    def test_names(self):
        mgr = TransactionManager()
        mgr._MustUse__silence = True

        class T:
            def __init__(self):
                Transaction(manager=mgr)

        T()
        self.assertEqual(mgr.transactions[0].name, "T")

        t = Transaction(name="x", manager=mgr)
        self.assertEqual(t.name, "x")

        t = Transaction(manager=mgr)
        self.assertEqual(t.name, "t")

        m = Method(name="x")
        self.assertEqual(m.name, "x")

        m = Method()
        self.assertEqual(m.name, "m")


class TestScheduler(TestCaseWithSimulator):
    def count_test(self, sched, cnt):
        self.assertEqual(sched.count, cnt)
        self.assertEqual(len(sched.requests), cnt)
        self.assertEqual(len(sched.grant), cnt)
        self.assertEqual(len(sched.valid), 1)

    def sim_step(self, sched, request, expected_grant):
        yield sched.requests.eq(request)
        yield

        if request == 0:
            self.assertFalse((yield sched.valid))
        else:
            self.assertEqual((yield sched.grant), expected_grant)
            self.assertTrue((yield sched.valid))

    def test_single(self):
        sched = Scheduler(1)
        self.count_test(sched, 1)

        def process():
            yield from self.sim_step(sched, 0, 0)
            yield from self.sim_step(sched, 1, 1)
            yield from self.sim_step(sched, 1, 1)
            yield from self.sim_step(sched, 0, 0)

        with self.runSimulation(sched) as sim:
            sim.add_sync_process(process)

    def test_multi(self):
        sched = Scheduler(4)
        self.count_test(sched, 4)

        def process():
            yield from self.sim_step(sched, 0b0000, 0b0000)
            yield from self.sim_step(sched, 0b1010, 0b0010)
            yield from self.sim_step(sched, 0b1010, 0b1000)
            yield from self.sim_step(sched, 0b1010, 0b0010)
            yield from self.sim_step(sched, 0b1001, 0b1000)
            yield from self.sim_step(sched, 0b1001, 0b0001)

            yield from self.sim_step(sched, 0b1111, 0b0010)
            yield from self.sim_step(sched, 0b1111, 0b0100)
            yield from self.sim_step(sched, 0b1111, 0b1000)
            yield from self.sim_step(sched, 0b1111, 0b0001)

            yield from self.sim_step(sched, 0b0000, 0b0000)
            yield from self.sim_step(sched, 0b0010, 0b0010)
            yield from self.sim_step(sched, 0b0010, 0b0010)

        with self.runSimulation(sched) as sim:
            sim.add_sync_process(process)


class TransactionConflictTestCircuit(Elaboratable):
    def __init__(self, scheduler):
        self.scheduler = scheduler

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m, TransactionManager(self.scheduler))
        adapter = Adapter(i=32, o=32)
        m.submodules.out = self.out = TestbenchIO(adapter)
        m.submodules.in1 = self.in1 = TestbenchIO(AdapterTrans(adapter.iface))
        m.submodules.in2 = self.in2 = TestbenchIO(AdapterTrans(adapter.iface))
        # so that Amaranth allows us to use add_clock
        dummy = Signal()
        m.d.sync += dummy.eq(1)
        return tm


@parameterized_class(
    ("name", "scheduler"),
    [
        ("trivial_roundrobin", trivial_roundrobin_cc_scheduler),
        ("eager_deterministic", eager_deterministic_cc_scheduler),
    ],
)
class TestTransactionConflict(TestCaseWithSimulator):
    scheduler: TransactionScheduler

    def setUp(self):
        self.in1_stream = range(0, 100)
        self.in2_stream = range(100, 200)
        self.out_stream = range(200, 400)
        self.in_expected = deque()
        self.out1_expected = deque()
        self.out2_expected = deque()
        self.m = TransactionConflictTestCircuit(self.__class__.scheduler)

        random.seed(42)

    def tearDown(self):
        assert not self.in_expected
        assert not self.out1_expected
        assert not self.out2_expected

    def make_process(
        self, io: TestbenchIO, prob: float, src: Iterable[int], tgt: Callable[[int], None], chk: Callable[[int], None]
    ):
        def process():
            for i in src:
                while random.random() >= prob:
                    yield
                tgt(i)
                r = yield from io.call({"data": i})
                chk(r["data"])

        return process

    def make_in1_process(self, prob: float):
        def tgt(x: int):
            self.out1_expected.append(x)

        def chk(x: int):
            self.assertEqual(x, self.in_expected.popleft())

        return self.make_process(self.m.in1, prob, self.in1_stream, tgt, chk)

    def make_in2_process(self, prob: float):
        def tgt(x: int):
            self.out2_expected.append(x)

        def chk(x: int):
            self.assertEqual(x, self.in_expected.popleft())

        return self.make_process(self.m.in2, prob, self.in2_stream, tgt, chk)

    def make_out_process(self, prob: float):
        def tgt(x: int):
            self.in_expected.append(x)

        def chk(x: int):
            if self.out1_expected and x == self.out1_expected[0]:
                self.out1_expected.popleft()
            elif self.out2_expected and x == self.out2_expected[0]:
                self.out2_expected.popleft()
            else:
                self.fail("%d not found in any of the queues" % x)

        return self.make_process(self.m.out, prob, self.out_stream, tgt, chk)

    @parameterized.expand(
        [
            ("fullcontention", 1, 1, 1),
            ("highcontention", 0.5, 0.5, 0.75),
            ("lowcontention", 0.1, 0.1, 0.5),
        ]
    )
    def test_calls(self, name, prob1, prob2, probout):
        def debug_signals():
            return {
                "in1": self.m.in1.debug_signals(),
                "in2": self.m.in2.debug_signals(),
                "out": self.m.out.debug_signals(),
            }

        with self.runSimulation(self.m, extra_signals=debug_signals) as sim:
            sim.add_sync_process(self.make_in1_process(prob1))
            sim.add_sync_process(self.make_in2_process(prob2))
            sim.add_sync_process(self.make_out_process(probout))
