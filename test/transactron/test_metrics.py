import json
import random
import queue
from typing import Type
from enum import IntFlag, IntEnum, auto, Enum

from parameterized import parameterized_class

from amaranth import *
from amaranth.sim import Settle

from transactron.lib.metrics import *
from transactron import *
from transactron.testing import TestCaseWithSimulator, data_layout, SimpleTestCircuit
from transactron.testing.infrastructure import Now
from transactron.utils.dependencies import DependencyContext


class CounterInMethodCircuit(Elaboratable):
    def __init__(self):
        self.method = Method()
        self.counter = HwCounter("in_method")

    def elaborate(self, platform):
        m = TModule()

        m.submodules.counter = self.counter

        @def_method(m, self.method)
        def _():
            self.counter.incr(m)

        return m


class CounterWithConditionInMethodCircuit(Elaboratable):
    def __init__(self):
        self.method = Method(i=[("cond", 1)])
        self.counter = HwCounter("with_condition_in_method")

    def elaborate(self, platform):
        m = TModule()

        m.submodules.counter = self.counter

        @def_method(m, self.method)
        def _(cond):
            self.counter.incr(m, cond=cond)

        return m


class CounterWithoutMethodCircuit(Elaboratable):
    def __init__(self):
        self.cond = Signal()
        self.counter = HwCounter("with_condition_without_method")

    def elaborate(self, platform):
        m = TModule()

        m.submodules.counter = self.counter

        with Transaction().body(m):
            self.counter.incr(m, cond=self.cond)

        return m


class TestHwCounter(TestCaseWithSimulator):
    def setup_method(self) -> None:
        random.seed(42)

    def test_counter_in_method(self):
        m = SimpleTestCircuit(CounterInMethodCircuit())
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        def test_process():
            called_cnt = 0
            for _ in range(200):
                call_now = random.randint(0, 1) == 0

                if call_now:
                    yield from m.method.call()
                else:
                    yield

                # Note that it takes one cycle to update the register value, so here
                # we are comparing the "previous" values.
                assert called_cnt == (yield m._dut.counter.count.value)

                if call_now:
                    called_cnt += 1

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)

    def test_counter_with_condition_in_method(self):
        m = SimpleTestCircuit(CounterWithConditionInMethodCircuit())
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        def test_process():
            called_cnt = 0
            for _ in range(200):
                call_now = random.randint(0, 1) == 0
                condition = random.randint(0, 1)

                if call_now:
                    yield from m.method.call(cond=condition)
                else:
                    yield

                # Note that it takes one cycle to update the register value, so here
                # we are comparing the "previous" values.
                assert called_cnt == (yield m._dut.counter.count.value)

                if call_now and condition == 1:
                    called_cnt += 1

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)

    def test_counter_with_condition_without_method(self):
        m = CounterWithoutMethodCircuit()
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        def test_process():
            called_cnt = 0
            for _ in range(200):
                condition = random.randint(0, 1)

                yield m.cond.eq(condition)
                yield

                # Note that it takes one cycle to update the register value, so here
                # we are comparing the "previous" values.
                assert called_cnt == (yield m.counter.count.value)

                if condition == 1:
                    called_cnt += 1

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)


class OneHotEnum(IntFlag):
    ADD = auto()
    XOR = auto()
    OR = auto()


class PlainIntEnum(IntEnum):
    TEST_1 = auto()
    TEST_2 = auto()
    TEST_3 = auto()


class TaggedCounterCircuit(Elaboratable):
    def __init__(self, tags: range | Type[Enum] | list[int]):
        self.counter = TaggedCounter("counter", "", tags=tags)

        self.cond = Signal()
        self.tag = Signal(self.counter.tag_width)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.counter = self.counter

        with Transaction().body(m):
            self.counter.incr(m, self.tag, cond=self.cond)

        return m


class TestTaggedCounter(TestCaseWithSimulator):
    def setup_method(self) -> None:
        random.seed(42)

    def do_test_enum(self, tags: range | Type[Enum] | list[int], tag_values: list[int]):
        m = TaggedCounterCircuit(tags)
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        counts: dict[int, int] = {}
        for i in tag_values:
            counts[i] = 0

        def test_process():
            for _ in range(200):
                for i in tag_values:
                    assert counts[i] == (yield m.counter.counters[i].value)

                tag = random.choice(list(tag_values))

                yield m.cond.eq(1)
                yield m.tag.eq(tag)
                yield
                yield m.cond.eq(0)
                yield

                counts[tag] += 1

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)

    def test_one_hot_enum(self):
        self.do_test_enum(OneHotEnum, [e.value for e in OneHotEnum])

    def test_plain_int_enum(self):
        self.do_test_enum(PlainIntEnum, [e.value for e in PlainIntEnum])

    def test_negative_range(self):
        r = range(-10, 15, 3)
        self.do_test_enum(r, list(r))

    def test_positive_range(self):
        r = range(0, 30, 2)
        self.do_test_enum(r, list(r))

    def test_value_list(self):
        values = [-2137, 2, 4, 8, 42]
        self.do_test_enum(values, values)


class ExpHistogramCircuit(Elaboratable):
    def __init__(self, bucket_cnt: int, sample_width: int):
        self.sample_width = sample_width

        self.method = Method(i=data_layout(32))
        self.histogram = HwExpHistogram("histogram", bucket_count=bucket_cnt, sample_width=sample_width)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.histogram = self.histogram

        @def_method(m, self.method)
        def _(data):
            self.histogram.add(m, data[0 : self.sample_width])

        return m


@parameterized_class(
    ("bucket_count", "sample_width"),
    [
        (5, 5),  # last bucket is [8, inf), max sample=31
        (8, 5),  # last bucket is [64, inf), max sample=31
        (8, 6),  # last bucket is [64, inf), max sample=63
        (8, 20),  # last bucket is [64, inf), max sample=big
    ],
)
class TestHwHistogram(TestCaseWithSimulator):
    bucket_count: int
    sample_width: int

    def test_histogram(self):
        random.seed(42)

        m = SimpleTestCircuit(ExpHistogramCircuit(bucket_cnt=self.bucket_count, sample_width=self.sample_width))
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        max_sample_value = 2**self.sample_width - 1

        def test_process():
            min = max_sample_value + 1
            max = 0
            sum = 0
            count = 0

            buckets = [0] * self.bucket_count

            for _ in range(500):
                if random.randrange(3) == 0:
                    value = random.randint(0, max_sample_value)
                    if value < min:
                        min = value
                    if value > max:
                        max = value
                    sum += value
                    count += 1
                    for i in range(self.bucket_count):
                        if value < 2**i or i == self.bucket_count - 1:
                            buckets[i] += 1
                            break
                    yield from m.method.call(data=value)
                    yield
                else:
                    yield

                histogram = m._dut.histogram
                # Skip the assertion if the min is still uninitialized
                if min != max_sample_value + 1:
                    assert min == (yield histogram.min.value)

                assert max == (yield histogram.max.value)
                assert sum == (yield histogram.sum.value)
                assert count == (yield histogram.count.value)

                total_count = 0
                for i in range(self.bucket_count):
                    bucket_value = yield histogram.buckets[i].value
                    total_count += bucket_value
                    assert buckets[i] == bucket_value

                # Sanity check if all buckets sum up to the total count value
                assert total_count == (yield histogram.count.value)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)


class TestLatencyMeasurerBase(TestCaseWithSimulator):
    def check_latencies(self, m: SimpleTestCircuit, latencies: list[int]):
        assert min(latencies) == (yield m._dut.histogram.min.value)
        assert max(latencies) == (yield m._dut.histogram.max.value)
        assert sum(latencies) == (yield m._dut.histogram.sum.value)
        assert len(latencies) == (yield m._dut.histogram.count.value)

        for i in range(m._dut.histogram.bucket_count):
            bucket_start = 0 if i == 0 else 2 ** (i - 1)
            bucket_end = 1e10 if i == m._dut.histogram.bucket_count - 1 else 2**i

            count = sum(1 for x in latencies if bucket_start <= x < bucket_end)
            assert count == (yield m._dut.histogram.buckets[i].value)


@parameterized_class(
    ("slots_number", "expected_consumer_wait"),
    [
        (2, 5),
        (2, 10),
        (5, 10),
        (10, 1),
        (10, 10),
        (5, 5),
    ],
)
class TestFIFOLatencyMeasurer(TestLatencyMeasurerBase):
    slots_number: int
    expected_consumer_wait: float

    def test_latency_measurer(self):
        random.seed(42)

        m = SimpleTestCircuit(FIFOLatencyMeasurer("latency", slots_number=self.slots_number, max_latency=300))
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        latencies: list[int] = []

        event_queue = queue.Queue()

        finish = False

        def producer():
            nonlocal finish

            for _ in range(200):
                yield from m._start.call()

                # Make sure that the time is updated first.
                yield Settle()
                time = yield Now()
                event_queue.put(time)
                yield from self.random_wait_geom(0.8)

            finish = True

        def consumer():
            while not finish:
                yield from m._stop.call()

                # Make sure that the time is updated first.
                yield Settle()
                time = yield Now()
                latencies.append(time - event_queue.get())

                yield from self.random_wait_geom(1.0 / self.expected_consumer_wait)

            self.check_latencies(m, latencies)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)


@parameterized_class(
    ("slots_number", "expected_consumer_wait"),
    [
        (2, 5),
        (2, 10),
        (5, 10),
        (10, 1),
        (10, 10),
        (5, 5),
    ],
)
class TestIndexedLatencyMeasurer(TestLatencyMeasurerBase):
    slots_number: int
    expected_consumer_wait: float

    def test_latency_measurer(self):
        random.seed(42)

        m = SimpleTestCircuit(TaggedLatencyMeasurer("latency", slots_number=self.slots_number, max_latency=300))
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        latencies: list[int] = []

        events = list(0 for _ in range(self.slots_number))
        free_slots = list(k for k in range(self.slots_number))
        used_slots: list[int] = []

        finish = False

        def producer():
            nonlocal finish

            for _ in range(200):
                while not free_slots:
                    yield
                    continue
                yield Settle()

                slot_id = random.choice(free_slots)
                yield from m._start.call(slot=slot_id)

                time = yield Now()

                events[slot_id] = time
                free_slots.remove(slot_id)
                used_slots.append(slot_id)

                yield from self.random_wait_geom(0.8)

            finish = True

        def consumer():
            while not finish:
                while not used_slots:
                    yield
                    continue

                slot_id = random.choice(used_slots)

                yield from m._stop.call(slot=slot_id)

                time = yield Now()

                yield Settle()
                yield Settle()

                latencies.append(time - events[slot_id])
                used_slots.remove(slot_id)
                free_slots.append(slot_id)

                yield from self.random_wait_geom(1.0 / self.expected_consumer_wait)

            self.check_latencies(m, latencies)

        with self.run_simulation(m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)


class MetricManagerTestCircuit(Elaboratable):
    def __init__(self):
        self.incr_counters = Method(i=[("counter1", 1), ("counter2", 1), ("counter3", 1)])

        self.counter1 = HwCounter("foo.counter1", "this is the description")
        self.counter2 = HwCounter("bar.baz.counter2")
        self.counter3 = HwCounter("bar.baz.counter3", "yet another description")

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.counter1, self.counter2, self.counter3]

        @def_method(m, self.incr_counters)
        def _(counter1, counter2, counter3):
            self.counter1.incr(m, cond=counter1)
            self.counter2.incr(m, cond=counter2)
            self.counter3.incr(m, cond=counter3)

        return m


class TestMetricsManager(TestCaseWithSimulator):
    def test_metrics_metadata(self):
        # We need to initialize the circuit to make sure that metrics are registered
        # in the dependency manager.
        m = MetricManagerTestCircuit()
        metrics_manager = HardwareMetricsManager()

        # Run the simulation so Amaranth doesn't scream that we have unused elaboratables.
        with self.run_simulation(m):
            pass

        assert metrics_manager.get_metrics()["foo.counter1"].to_json() == json.dumps(  # type: ignore
            {
                "fully_qualified_name": "foo.counter1",
                "description": "this is the description",
                "regs": {"count": {"name": "count", "description": "the value of the counter", "width": 32}},
            }
        )

        assert metrics_manager.get_metrics()["bar.baz.counter2"].to_json() == json.dumps(  # type: ignore
            {
                "fully_qualified_name": "bar.baz.counter2",
                "description": "",
                "regs": {"count": {"name": "count", "description": "the value of the counter", "width": 32}},
            }
        )

        assert metrics_manager.get_metrics()["bar.baz.counter3"].to_json() == json.dumps(  # type: ignore
            {
                "fully_qualified_name": "bar.baz.counter3",
                "description": "yet another description",
                "regs": {"count": {"name": "count", "description": "the value of the counter", "width": 32}},
            }
        )

    def test_returned_reg_values(self):
        random.seed(42)

        m = SimpleTestCircuit(MetricManagerTestCircuit())
        metrics_manager = HardwareMetricsManager()

        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        def test_process():
            counters = [0] * 3
            for _ in range(200):
                rand = [random.randint(0, 1) for _ in range(3)]

                yield from m.incr_counters.call(counter1=rand[0], counter2=rand[1], counter3=rand[2])
                yield

                for i in range(3):
                    if rand[i] == 1:
                        counters[i] += 1

                assert counters[0] == (yield metrics_manager.get_register_value("foo.counter1", "count"))
                assert counters[1] == (yield metrics_manager.get_register_value("bar.baz.counter2", "count"))
                assert counters[2] == (yield metrics_manager.get_register_value("bar.baz.counter3", "count"))

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)
