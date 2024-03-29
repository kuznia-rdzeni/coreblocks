import json
import random
import queue
from parameterized import parameterized_class

from amaranth import *
from amaranth.sim import Passive, Settle

from transactron.lib.metrics import *
from transactron import *
from transactron.testing import TestCaseWithSimulator, data_layout, SimpleTestCircuit
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
    def setUp(self) -> None:
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
                self.assertEqual(called_cnt, (yield m._dut.counter.count.value))

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
                self.assertEqual(called_cnt, (yield m._dut.counter.count.value))

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
                self.assertEqual(called_cnt, (yield m.counter.count.value))

                if condition == 1:
                    called_cnt += 1

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)


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
                    self.assertEqual(min, (yield histogram.min.value))

                self.assertEqual(max, (yield histogram.max.value))
                self.assertEqual(sum, (yield histogram.sum.value))
                self.assertEqual(count, (yield histogram.count.value))

                total_count = 0
                for i in range(self.bucket_count):
                    bucket_value = yield histogram.buckets[i].value
                    total_count += bucket_value
                    self.assertEqual(buckets[i], bucket_value)

                # Sanity check if all buckets sum up to the total count value
                self.assertEqual(total_count, (yield histogram.count.value))

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)


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
class TestLatencyMeasurer(TestCaseWithSimulator):
    slots_number: int
    expected_consumer_wait: float

    def test_latency_measurer(self):
        random.seed(42)

        m = SimpleTestCircuit(LatencyMeasurer("latency", slots_number=self.slots_number, max_latency=300))
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)

        latencies: list[int] = []

        event_queue = queue.Queue()

        time = 0

        def ticker():
            nonlocal time

            yield Passive()

            while True:
                yield
                time += 1

        finish = False

        def producer():
            nonlocal finish

            for _ in range(200):
                yield from m._start.call()

                # Make sure that the time is updated first.
                yield Settle()
                event_queue.put(time)
                yield from self.random_wait_geom(0.8)

            finish = True

        def consumer():
            while not finish:
                yield from m._stop.call()

                # Make sure that the time is updated first.
                yield Settle()
                latencies.append(time - event_queue.get())

                yield from self.random_wait_geom(1.0 / self.expected_consumer_wait)

            self.assertEqual(min(latencies), (yield m._dut.histogram.min.value))
            self.assertEqual(max(latencies), (yield m._dut.histogram.max.value))
            self.assertEqual(sum(latencies), (yield m._dut.histogram.sum.value))
            self.assertEqual(len(latencies), (yield m._dut.histogram.count.value))

            for i in range(m._dut.histogram.bucket_count):
                bucket_start = 0 if i == 0 else 2 ** (i - 1)
                bucket_end = 1e10 if i == m._dut.histogram.bucket_count - 1 else 2**i

                count = sum(1 for x in latencies if bucket_start <= x < bucket_end)
                self.assertEqual(count, (yield m._dut.histogram.buckets[i].value))

        with self.run_simulation(m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
            sim.add_sync_process(ticker)


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

        self.assertEqual(
            metrics_manager.get_metrics()["foo.counter1"].to_json(),  # type: ignore
            json.dumps(
                {
                    "fully_qualified_name": "foo.counter1",
                    "description": "this is the description",
                    "regs": {"count": {"name": "count", "description": "the value of the counter", "width": 32}},
                }
            ),
        )

        self.assertEqual(
            metrics_manager.get_metrics()["bar.baz.counter2"].to_json(),  # type: ignore
            json.dumps(
                {
                    "fully_qualified_name": "bar.baz.counter2",
                    "description": "",
                    "regs": {"count": {"name": "count", "description": "the value of the counter", "width": 32}},
                }
            ),
        )

        self.assertEqual(
            metrics_manager.get_metrics()["bar.baz.counter3"].to_json(),  # type: ignore
            json.dumps(
                {
                    "fully_qualified_name": "bar.baz.counter3",
                    "description": "yet another description",
                    "regs": {"count": {"name": "count", "description": "the value of the counter", "width": 32}},
                }
            ),
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

                self.assertEqual(counters[0], (yield metrics_manager.get_register_value("foo.counter1", "count")))
                self.assertEqual(counters[1], (yield metrics_manager.get_register_value("bar.baz.counter2", "count")))
                self.assertEqual(counters[2], (yield metrics_manager.get_register_value("bar.baz.counter3", "count")))

        with self.run_simulation(m) as sim:
            sim.add_sync_process(test_process)
