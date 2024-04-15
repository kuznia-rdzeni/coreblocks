from unittest.case import TestCase
import pytest
from amaranth import *
from amaranth.sim import *

import random
import contextlib

from collections import deque
from typing import Iterable, Callable
from parameterized import parameterized, parameterized_class

from transactron.testing import TestCaseWithSimulator, TestbenchIO, data_layout

from transactron import *
from transactron.lib import Adapter, AdapterTrans
from transactron.utils import Scheduler

from transactron.core import Priority
from transactron.core.schedulers import trivial_roundrobin_cc_scheduler, eager_deterministic_cc_scheduler
from transactron.core.manager import TransactionScheduler
from transactron.utils.dependencies import DependencyContext


class TestNames(TestCase):
    def test_names(self):
        mgr = TransactionManager()
        mgr._MustUse__silence = True  # type: ignore

        class T(Elaboratable):
            def __init__(self):
                self._MustUse__silence = True  # type: ignore
                Transaction(manager=mgr)

        T()
        assert mgr.transactions[0].name == "T"

        t = Transaction(name="x", manager=mgr)
        assert t.name == "x"

        t = Transaction(manager=mgr)
        assert t.name == "t"

        m = Method(name="x")
        assert m.name == "x"

        m = Method()
        assert m.name == "m"


class TestScheduler(TestCaseWithSimulator):
    def count_test(self, sched, cnt):
        assert sched.count == cnt
        assert len(sched.requests) == cnt
        assert len(sched.grant) == cnt
        assert len(sched.valid) == 1

    def sim_step(self, sched, request, expected_grant):
        yield sched.requests.eq(request)
        yield

        if request == 0:
            assert not (yield sched.valid)
        else:
            assert (yield sched.grant) == expected_grant
            assert (yield sched.valid)

    def test_single(self):
        sched = Scheduler(1)
        self.count_test(sched, 1)

        def process():
            yield from self.sim_step(sched, 0, 0)
            yield from self.sim_step(sched, 1, 1)
            yield from self.sim_step(sched, 1, 1)
            yield from self.sim_step(sched, 0, 0)

        with self.run_simulation(sched) as sim:
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

        with self.run_simulation(sched) as sim:
            sim.add_sync_process(process)


class TransactionConflictTestCircuit(Elaboratable):
    def __init__(self, scheduler):
        self.scheduler = scheduler

    def elaborate(self, platform):
        m = TModule()
        tm = TransactionModule(m, DependencyContext.get(), TransactionManager(self.scheduler))
        adapter = Adapter(i=data_layout(32), o=data_layout(32))
        m.submodules.out = self.out = TestbenchIO(adapter)
        m.submodules.in1 = self.in1 = TestbenchIO(AdapterTrans(adapter.iface))
        m.submodules.in2 = self.in2 = TestbenchIO(AdapterTrans(adapter.iface))
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

    def setup_method(self):
        random.seed(42)

    def make_process(
        self, io: TestbenchIO, prob: float, src: Iterable[int], tgt: Callable[[int], None], chk: Callable[[int], None]
    ):
        def process():
            for i in src:
                while random.random() >= prob:
                    yield
                tgt(i)
                r = yield from io.call(data=i)
                chk(r["data"])

        return process

    def make_in1_process(self, prob: float):
        def tgt(x: int):
            self.out1_expected.append(x)

        def chk(x: int):
            assert x == self.in_expected.popleft()

        return self.make_process(self.m.in1, prob, self.in1_stream, tgt, chk)

    def make_in2_process(self, prob: float):
        def tgt(x: int):
            self.out2_expected.append(x)

        def chk(x: int):
            assert x == self.in_expected.popleft()

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
                assert False, "%d not found in any of the queues" % x

        return self.make_process(self.m.out, prob, self.out_stream, tgt, chk)

    @parameterized.expand(
        [
            ("fullcontention", 1, 1, 1),
            ("highcontention", 0.5, 0.5, 0.75),
            ("lowcontention", 0.1, 0.1, 0.5),
        ]
    )
    def test_calls(self, name, prob1, prob2, probout):
        self.in1_stream = range(0, 100)
        self.in2_stream = range(100, 200)
        self.out_stream = range(200, 400)
        self.in_expected = deque()
        self.out1_expected = deque()
        self.out2_expected = deque()
        self.m = TransactionConflictTestCircuit(self.__class__.scheduler)

        with self.run_simulation(self.m, add_transaction_module=False) as sim:
            sim.add_sync_process(self.make_in1_process(prob1))
            sim.add_sync_process(self.make_in2_process(prob2))
            sim.add_sync_process(self.make_out_process(probout))

        assert not self.in_expected
        assert not self.out1_expected
        assert not self.out2_expected


class SchedulingTestCircuit(Elaboratable):
    def __init__(self):
        self.r1 = Signal()
        self.r2 = Signal()
        self.t1 = Signal()
        self.t2 = Signal()


class PriorityTestCircuit(SchedulingTestCircuit):
    def __init__(self, priority: Priority, unsatisfiable=False):
        super().__init__()
        self.priority = priority
        self.unsatisfiable = unsatisfiable

    def make_relations(self, t1: Transaction | Method, t2: Transaction | Method):
        t1.add_conflict(t2, self.priority)
        if self.unsatisfiable:
            t2.add_conflict(t1, self.priority)


class TransactionPriorityTestCircuit(PriorityTestCircuit):
    def elaborate(self, platform):
        m = TModule()

        transaction1 = Transaction()
        transaction2 = Transaction()

        with transaction1.body(m, request=self.r1):
            m.d.comb += self.t1.eq(1)

        with transaction2.body(m, request=self.r2):
            m.d.comb += self.t2.eq(1)

        self.make_relations(transaction1, transaction2)

        return m


class MethodPriorityTestCircuit(PriorityTestCircuit):
    def elaborate(self, platform):
        m = TModule()

        method1 = Method()
        method2 = Method()

        @def_method(m, method1, ready=self.r1)
        def _():
            m.d.comb += self.t1.eq(1)

        @def_method(m, method2, ready=self.r2)
        def _():
            m.d.comb += self.t2.eq(1)

        with Transaction().body(m):
            method1(m)

        with Transaction().body(m):
            method2(m)

        self.make_relations(method1, method2)

        return m


@parameterized_class(
    ("name", "circuit"), [("transaction", TransactionPriorityTestCircuit), ("method", MethodPriorityTestCircuit)]
)
class TestTransactionPriorities(TestCaseWithSimulator):
    circuit: type[PriorityTestCircuit]

    def setup_method(self):
        random.seed(42)

    @parameterized.expand([(Priority.UNDEFINED,), (Priority.LEFT,), (Priority.RIGHT,)])
    def test_priorities(self, priority: Priority):
        m = self.circuit(priority)

        def process():
            to_do = 5 * [(0, 1), (1, 0), (1, 1)]
            random.shuffle(to_do)
            for r1, r2 in to_do:
                yield m.r1.eq(r1)
                yield m.r2.eq(r2)
                yield Settle()
                assert (yield m.t1) != (yield m.t2)
                if r1 == 1 and r2 == 1:
                    if priority == Priority.LEFT:
                        assert (yield m.t1)
                    if priority == Priority.RIGHT:
                        assert (yield m.t2)

        with self.run_simulation(m) as sim:
            sim.add_process(process)

    @parameterized.expand([(Priority.UNDEFINED,), (Priority.LEFT,), (Priority.RIGHT,)])
    def test_unsatisfiable(self, priority: Priority):
        m = self.circuit(priority, True)

        import graphlib

        if priority != Priority.UNDEFINED:
            cm = pytest.raises(graphlib.CycleError)
        else:
            cm = contextlib.nullcontext()

        with cm:
            with self.run_simulation(m):
                pass


class NestedTransactionsTestCircuit(SchedulingTestCircuit):
    def elaborate(self, platform):
        m = TModule()
        tm = TransactionModule(m)

        with tm.context():
            with Transaction().body(m, request=self.r1):
                m.d.comb += self.t1.eq(1)
                with Transaction().body(m, request=self.r2):
                    m.d.comb += self.t2.eq(1)

        return tm


class NestedMethodsTestCircuit(SchedulingTestCircuit):
    def elaborate(self, platform):
        m = TModule()
        tm = TransactionModule(m)

        method1 = Method()
        method2 = Method()

        @def_method(m, method1, ready=self.r1)
        def _():
            m.d.comb += self.t1.eq(1)

            @def_method(m, method2, ready=self.r2)
            def _():
                m.d.comb += self.t2.eq(1)

        with tm.context():
            with Transaction().body(m):
                method1(m)

            with Transaction().body(m):
                method2(m)

        return tm


@parameterized_class(
    ("name", "circuit"), [("transaction", NestedTransactionsTestCircuit), ("method", NestedMethodsTestCircuit)]
)
class TestNested(TestCaseWithSimulator):
    circuit: type[SchedulingTestCircuit]

    def setup_method(self):
        random.seed(42)

    def test_scheduling(self):
        m = self.circuit()

        def process():
            to_do = 5 * [(0, 1), (1, 0), (1, 1)]
            random.shuffle(to_do)
            for r1, r2 in to_do:
                yield m.r1.eq(r1)
                yield m.r2.eq(r2)
                yield
                assert (yield m.t1) == r1
                assert (yield m.t2) == r1 * r2

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)


class ScheduleBeforeTestCircuit(SchedulingTestCircuit):
    def elaborate(self, platform):
        m = TModule()
        tm = TransactionModule(m)

        method = Method()

        @def_method(m, method)
        def _():
            pass

        with tm.context():
            with (t1 := Transaction()).body(m, request=self.r1):
                method(m)
                m.d.comb += self.t1.eq(1)

            with (t2 := Transaction()).body(m, request=self.r2 & t1.grant):
                method(m)
                m.d.comb += self.t2.eq(1)

            t1.schedule_before(t2)

        return tm


class TestScheduleBefore(TestCaseWithSimulator):
    def setup_method(self):
        random.seed(42)

    def test_schedule_before(self):
        m = ScheduleBeforeTestCircuit()

        def process():
            to_do = 5 * [(0, 1), (1, 0), (1, 1)]
            random.shuffle(to_do)
            for r1, r2 in to_do:
                yield m.r1.eq(r1)
                yield m.r2.eq(r2)
                yield
                assert (yield m.t1) == r1
                assert not (yield m.t2)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(process)


class SingleCallerTestCircuit(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        method = Method(single_caller=True)

        with Transaction().body(m):
            method(m)

        with Transaction().body(m):
            method(m)

        return m


class TestSingleCaller(TestCaseWithSimulator):
    def test_single_caller(self):
        m = SingleCallerTestCircuit()

        with pytest.raises(RuntimeError):
            with self.run_simulation(m):
                pass
