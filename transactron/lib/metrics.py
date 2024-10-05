from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from typing import Optional, Type
from abc import ABC
from enum import Enum

from amaranth import *
from amaranth.utils import bits_for, ceil_log2, exact_log2

from transactron.utils import ValueLike, OneHotSwitchDynamic, SignalBundle
from transactron import Method, def_method, TModule
from transactron.lib import FIFO, AsyncMemoryBank, logging
from transactron.utils.dependencies import ListKey, DependencyContext, SimpleKey

__all__ = [
    "MetricRegisterModel",
    "MetricModel",
    "HwMetric",
    "HwCounter",
    "TaggedCounter",
    "HwExpHistogram",
    "FIFOLatencyMeasurer",
    "TaggedLatencyMeasurer",
    "HardwareMetricsManager",
    "HwMetricsEnabledKey",
]


@dataclass_json
@dataclass(frozen=True)
class MetricRegisterModel:
    """
    Represents a single register of a metric, serving as a fundamental
    building block that holds a singular value.

    Attributes
    ----------
    name: str
        The unique identifier for the register (among remaning
        registers of a specific metric).
    description: str
        A brief description of the metric's purpose.
    width: int
        The bit-width of the register.
    """

    name: str
    description: str
    width: int


@dataclass_json
@dataclass
class MetricModel:
    """
    Provides information about a metric exposed by the circuit. Each metric
    comprises multiple registers, each dedicated to storing specific values.

    The configuration of registers is internally determined by a
    specific metric type and is not user-configurable.

    Attributes
    ----------
    fully_qualified_name: str
        The fully qualified name of the metric, with name components joined by dots ('.'),
        e.g., 'foo.bar.requests'.
    description: str
        A human-readable description of the metric's functionality.
    regs: list[MetricRegisterModel]
        A list of registers associated with the metric.
    """

    fully_qualified_name: str
    description: str
    regs: dict[str, MetricRegisterModel] = field(default_factory=dict)


class HwMetricRegister(MetricRegisterModel):
    """
    A concrete implementation of a metric register that holds its value as Amaranth signal.

    Attributes
    ----------
    value: Signal
        Amaranth signal representing the value of the register.
    """

    def __init__(self, name: str, width_bits: int, description: str = "", init: int = 0):
        """
        Parameters
        ----------
        name: str
            The unique identifier for the register (among remaning
            registers of a specific metric).
        width: int
            The bit-width of the register.
        description: str
            A brief description of the metric's purpose.
        init: int
            The reset value of the register.
        """
        super().__init__(name, description, width_bits)

        self.value = Signal(width_bits, init=init, name=name)


@dataclass(frozen=True)
class HwMetricsListKey(ListKey["HwMetric"]):
    """DependencyManager key collecting hardware metrics globally as a list."""

    pass


@dataclass(frozen=True)
class HwMetricsEnabledKey(SimpleKey[bool]):
    """
    DependencyManager key for enabling hardware metrics. If metrics are disabled,
    none of theirs signals will be synthesized.
    """

    lock_on_get = False
    empty_valid = True
    default_value = False


class HwMetric(ABC, MetricModel):
    """
    A base for all metric implementations. It should be only used for declaring
    new types of metrics.

    It takes care of registering the metric in the dependency manager.

    Attributes
    ----------
    signals: dict[str, Signal]
        A mapping from a register name to a Signal containing the value of that register.
    """

    def __init__(self, fully_qualified_name: str, description: str):
        """
        Parameters
        ----------
        fully_qualified_name: str
            The fully qualified name of the metric.
        description: str
            A human-readable description of the metric's functionality.
        """
        super().__init__(fully_qualified_name, description)

        self.signals: dict[str, Signal] = {}

        # add the metric to the global list of all metrics
        DependencyContext.get().add_dependency(HwMetricsListKey(), self)

        # So Amaranth doesn't report that the module is unused when metrics are disabled
        self._MustUse__silence = True  # type: ignore

    def add_registers(self, regs: list[HwMetricRegister]):
        """
        Adds registers to a metric. Should be only called by inheriting classes
        during initialization.

        Parameters
        ----------
        regs: list[HwMetricRegister]
            A list of registers to be registered.
        """
        for reg in regs:
            if reg.name in self.regs:
                raise RuntimeError(f"Register {reg.name}' is already added to the metric {self.fully_qualified_name}")

            self.regs[reg.name] = reg
            self.signals[reg.name] = reg.value

    def metrics_enabled(self) -> bool:
        return DependencyContext.get().get_dependency(HwMetricsEnabledKey())

    # To restore hashability lost by dataclass subclassing
    def __hash__(self):
        return object.__hash__(self)


class HwCounter(Elaboratable, HwMetric):
    """Hardware Counter

    The most basic hardware metric that can just increase its value.
    """

    def __init__(self, fully_qualified_name: str, description: str = "", *, width_bits: int = 32):
        """
        Parameters
        ----------
        fully_qualified_name: str
            The fully qualified name of the metric.
        description: str
            A human-readable description of the metric's functionality.
        width_bits: int
            The bit-width of the register. Defaults to 32 bits.
        """

        super().__init__(fully_qualified_name, description)

        self.count = HwMetricRegister("count", width_bits, "the value of the counter")

        self.add_registers([self.count])

        self._incr = Method()

    def elaborate(self, platform):
        if not self.metrics_enabled():
            return TModule()

        m = TModule()

        @def_method(m, self._incr)
        def _():
            m.d.sync += self.count.value.eq(self.count.value + 1)

        return m

    def incr(self, m: TModule, *, cond: ValueLike = C(1)):
        """
        Increases the value of the counter by 1.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        """
        if not self.metrics_enabled():
            return

        with m.If(cond):
            self._incr(m)


class TaggedCounter(Elaboratable, HwMetric):
    """Hardware Tagged Counter

    Like HwCounter, but contains multiple counters, each with its own tag.
    At a time a single counter can be increased and the value of the tag
    can be provided dynamically. The type of the tag can be either an int
    enum, a range or a list of integers (negative numbers are ok).

    Internally, it detects if tag values can be one-hot encoded and if so,
    it generates more optimized circuit.

    Attributes
    ----------
    tag_width: int
        The length of the signal holding a tag value.
    one_hot: bool
        Whether tag values can be one-hot encoded.
    counters: dict[int, HwMetricRegisters]
        Mapping from a tag value to a register holding a counter for that tag.
    """

    def __init__(
        self,
        fully_qualified_name: str,
        description: str = "",
        *,
        tags: range | Type[Enum] | list[int],
        registers_width: int = 32,
    ):
        """
        Parameters
        ----------
        fully_qualified_name: str
            The fully qualified name of the metric.
        description: str
            A human-readable description of the metric's functionality.
        tags: range | Type[Enum] | list[int]
            Tag values.
        registers_width: int
            Width of the underlying registers. Defaults to 32 bits.
        """

        super().__init__(fully_qualified_name, description)

        if isinstance(tags, range) or isinstance(tags, list):
            counters_meta = [(i, f"{i}") for i in tags]
        else:
            counters_meta = [(i.value, i.name) for i in tags]

        values = [value for value, _ in counters_meta]
        self.tag_width = max(bits_for(max(values)), bits_for(min(values)))

        self.one_hot = True
        negative_values = False
        for value in values:
            if value < 0:
                self.one_hot = False
                negative_values = True
                break

            log = ceil_log2(value)
            if 2**log != value:
                self.one_hot = False

        self._incr = Method(i=[("tag", Shape(self.tag_width, signed=negative_values))])

        self.counters: dict[int, HwMetricRegister] = {}
        for tag_value, name in counters_meta:
            value_str = ("1<<" + str(exact_log2(tag_value))) if self.one_hot else str(tag_value)
            description = f"the counter for tag {name} (value={value_str})"

            self.counters[tag_value] = HwMetricRegister(
                name,
                registers_width,
                description,
            )

        self.add_registers(list(self.counters.values()))

    def elaborate(self, platform):
        if not self.metrics_enabled():
            return TModule()

        m = TModule()

        @def_method(m, self._incr)
        def _(tag):
            if self.one_hot:
                sorted_tags = sorted(list(self.counters.keys()))
                for i in OneHotSwitchDynamic(m, tag):
                    counter = self.counters[sorted_tags[i]]
                    m.d.sync += counter.value.eq(counter.value + 1)
            else:
                for tag_value, counter in self.counters.items():
                    with m.If(tag == tag_value):
                        m.d.sync += counter.value.eq(counter.value + 1)

        return m

    def incr(self, m: TModule, tag: ValueLike, *, cond: ValueLike = C(1)):
        """
        Increases the counter of a given tag by 1.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        tag: ValueLike
            The tag of the counter.
        cond: ValueLike
            When set to high, the counter will be increased. By default set to high.
        """
        if not self.metrics_enabled():
            return

        with m.If(cond):
            self._incr(m, tag)


class HwExpHistogram(Elaboratable, HwMetric):
    """Hardware Exponential Histogram

    Represents the distribution of sampled data through a histogram. A histogram
    samples observations (usually things like request durations or queue sizes) and counts
    them in a configurable number of buckets. The buckets are of exponential size. For example,
    a histogram with 5 buckets would have the following value ranges:
    [0, 1); [1, 2); [2, 4); [4, 8); [8, +inf).

    Additionally, the histogram tracks the number of observations, the sum
    of observed values, and the minimum and maximum values.
    """

    def __init__(
        self,
        fully_qualified_name: str,
        description: str = "",
        *,
        bucket_count: int,
        sample_width: int = 32,
        registers_width: int = 32,
    ):
        """
        Parameters
        ----------
        fully_qualified_name: str
            The fully qualified name of the metric.
        description: str
            A human-readable description of the metric's functionality.
        max_value: int
            The maximum value that the histogram would be able to count. This
            value is used to calculate the number of buckets.
        """

        super().__init__(fully_qualified_name, description)
        self.bucket_count = bucket_count
        self.sample_width = sample_width

        self._add = Method(i=[("sample", self.sample_width)])

        self.count = HwMetricRegister("count", registers_width, "the count of events that have been observed")
        self.sum = HwMetricRegister("sum", registers_width, "the total sum of all observed values")
        self.min = HwMetricRegister(
            "min",
            self.sample_width,
            "the minimum of all observed values",
            init=(1 << self.sample_width) - 1,
        )
        self.max = HwMetricRegister("max", self.sample_width, "the maximum of all observed values")

        self.buckets = []
        for i in range(self.bucket_count):
            bucket_start = 0 if i == 0 else 2 ** (i - 1)
            bucket_end = "inf" if i == self.bucket_count - 1 else 2**i

            self.buckets.append(
                HwMetricRegister(
                    f"bucket-{bucket_end}",
                    registers_width,
                    f"the cumulative counter for the observation bucket [{bucket_start}, {bucket_end})",
                )
            )

        self.add_registers([self.count, self.sum, self.max, self.min] + self.buckets)

    def elaborate(self, platform):
        if not self.metrics_enabled():
            return TModule()

        m = TModule()

        @def_method(m, self._add)
        def _(sample):
            m.d.sync += self.count.value.eq(self.count.value + 1)
            m.d.sync += self.sum.value.eq(self.sum.value + sample)

            with m.If(sample > self.max.value):
                m.d.sync += self.max.value.eq(sample)

            with m.If(sample < self.min.value):
                m.d.sync += self.min.value.eq(sample)

            # todo: perhaps replace with a recursive implementation of the priority encoder
            bucket_idx = Signal(range(self.sample_width))
            for i in range(self.sample_width):
                with m.If(sample[i]):
                    m.d.av_comb += bucket_idx.eq(i)

            for i, bucket in enumerate(self.buckets):
                should_incr = C(0)
                if i == 0:
                    # The first bucket has a range [0, 1).
                    should_incr = sample == 0
                elif i == self.bucket_count - 1:
                    # The last bucket should count values bigger or equal to 2**(self.bucket_count-1)
                    should_incr = (bucket_idx >= i - 1) & (sample != 0)
                else:
                    should_incr = (bucket_idx == i - 1) & (sample != 0)

                with m.If(should_incr):
                    m.d.sync += bucket.value.eq(bucket.value + 1)

        return m

    def add(self, m: TModule, sample: Value):
        """
        Adds a new sample to the histogram.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        sample: ValueLike
            The value that will be added to the histogram
        """

        if not self.metrics_enabled():
            return

        self._add(m, sample)


class FIFOLatencyMeasurer(Elaboratable):
    """
    Measures duration between two events, e.g. request processing latency.
    It can track multiple events at the same time, i.e. the second event can
    be registered as started, before the first finishes. However, they must be
    processed in the FIFO order.

    The module exposes an exponential histogram of the measured latencies.
    """

    def __init__(
        self,
        fully_qualified_name: str,
        description: str = "",
        *,
        slots_number: int,
        max_latency: int,
    ):
        """
        Parameters
        ----------
        fully_qualified_name: str
            The fully qualified name of the metric.
        description: str
            A human-readable description of the metric's functionality.
        slots_number: int
            A number of events that the module can track simultaneously.
        max_latency: int
            The maximum latency of an event. Used to set signal widths and
            number of buckets in the histogram. If a latency turns to be
            bigger than the maximum, it will overflow and result in a false
            measurement.
        """
        self.fully_qualified_name = fully_qualified_name
        self.description = description
        self.slots_number = slots_number
        self.max_latency = max_latency

        self._start = Method()
        self._stop = Method()

        # This bucket count gives us the best possible granularity.
        bucket_count = bits_for(self.max_latency) + 1
        self.histogram = HwExpHistogram(
            self.fully_qualified_name,
            self.description,
            bucket_count=bucket_count,
            sample_width=bits_for(self.max_latency),
        )

    def elaborate(self, platform):
        if not self.metrics_enabled():
            return TModule()

        m = TModule()

        epoch_width = bits_for(self.max_latency)

        m.submodules.fifo = self.fifo = FIFO([("epoch", epoch_width)], self.slots_number)
        m.submodules.histogram = self.histogram

        epoch = Signal(epoch_width)

        m.d.sync += epoch.eq(epoch + 1)

        @def_method(m, self._start)
        def _():
            self.fifo.write(m, epoch)

        @def_method(m, self._stop)
        def _():
            ret = self.fifo.read(m)
            # The result of substracting two unsigned n-bit is a signed (n+1)-bit value,
            # so we need to cast the result and discard the most significant bit.
            duration = (epoch - ret.epoch).as_unsigned()[:-1]
            self.histogram.add(m, duration)

        return m

    def start(self, m: TModule):
        """
        Registers the start of an event. Can be called before the previous events
        finish. If there are no slots available, the method will be blocked.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        """

        if not self.metrics_enabled():
            return

        self._start(m)

    def stop(self, m: TModule):
        """
        Registers the end of the oldest event (the FIFO order). If there are no
        started events in the queue, the method will block.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        """

        if not self.metrics_enabled():
            return

        self._stop(m)

    def metrics_enabled(self) -> bool:
        return DependencyContext.get().get_dependency(HwMetricsEnabledKey())


class TaggedLatencyMeasurer(Elaboratable):
    """
    Measures duration between two events, e.g. request processing latency.
    It can track multiple events at the same time, i.e. the second event can
    be registered as started, before the first finishes. However, each event
    needs to have an unique slot tag.

    The module exposes an exponential histogram of the measured latencies.
    """

    def __init__(
        self,
        fully_qualified_name: str,
        description: str = "",
        *,
        slots_number: int,
        max_latency: int,
    ):
        """
        Parameters
        ----------
        fully_qualified_name: str
            The fully qualified name of the metric.
        description: str
            A human-readable description of the metric's functionality.
        slots_number: int
            A number of events that the module can track simultaneously.
        max_latency: int
            The maximum latency of an event. Used to set signal widths and
            number of buckets in the histogram. If a latency turns to be
            bigger than the maximum, it will overflow and result in a false
            measurement.
        """
        self.fully_qualified_name = fully_qualified_name
        self.description = description
        self.slots_number = slots_number
        self.max_latency = max_latency

        self._start = Method(i=[("slot", range(0, slots_number))])
        self._stop = Method(i=[("slot", range(0, slots_number))])

        # This bucket count gives us the best possible granularity.
        bucket_count = bits_for(self.max_latency) + 1
        self.histogram = HwExpHistogram(
            self.fully_qualified_name,
            self.description,
            bucket_count=bucket_count,
            sample_width=bits_for(self.max_latency),
        )

        self.log = logging.HardwareLogger(fully_qualified_name)

    def elaborate(self, platform):
        if not self.metrics_enabled():
            return TModule()

        m = TModule()

        epoch_width = bits_for(self.max_latency)

        m.submodules.slots = self.slots = AsyncMemoryBank(
            data_layout=[("epoch", epoch_width)], elem_count=self.slots_number
        )
        m.submodules.histogram = self.histogram

        slots_taken = Signal(self.slots_number)
        slots_taken_start = Signal.like(slots_taken)
        slots_taken_stop = Signal.like(slots_taken)

        m.d.comb += slots_taken_start.eq(slots_taken)
        m.d.comb += slots_taken_stop.eq(slots_taken_start)
        m.d.sync += slots_taken.eq(slots_taken_stop)

        epoch = Signal(epoch_width)

        m.d.sync += epoch.eq(epoch + 1)

        @def_method(m, self._start)
        def _(slot: Value):
            m.d.comb += slots_taken_start.eq(slots_taken | (1 << slot))
            self.log.error(m, (slots_taken & (1 << slot)).any(), "taken slot {} taken again", slot)
            self.slots.write(m, addr=slot, data=epoch)

        @def_method(m, self._stop)
        def _(slot: Value):
            m.d.comb += slots_taken_stop.eq(slots_taken_start & ~(C(1, self.slots_number) << slot))
            self.log.error(m, ~(slots_taken & (1 << slot)).any(), "free slot {} freed again", slot)
            ret = self.slots.read(m, addr=slot)
            # The result of substracting two unsigned n-bit is a signed (n+1)-bit value,
            # so we need to cast the result and discard the most significant bit.
            duration = (epoch - ret.epoch).as_unsigned()[:-1]
            self.histogram.add(m, duration)

        return m

    def start(self, m: TModule, *, slot: ValueLike):
        """
        Registers the start of an event for a given slot tag.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        slot: ValueLike
            The slot tag of the event.
        """

        if not self.metrics_enabled():
            return

        self._start(m, slot)

    def stop(self, m: TModule, *, slot: ValueLike):
        """
        Registers the end of the event for a given slot tag.

        Should be called in the body of either a transaction or a method.

        Parameters
        ----------
        m: TModule
            Transactron module
        slot: ValueLike
            The slot tag of the event.
        """

        if not self.metrics_enabled():
            return

        self._stop(m, slot)

    def metrics_enabled(self) -> bool:
        return DependencyContext.get().get_dependency(HwMetricsEnabledKey())


class HardwareMetricsManager:
    """
    Collects all metrics registered in the circuit and provides an easy
    access to them.
    """

    def __init__(self):
        self._metrics: Optional[dict[str, HwMetric]] = None

    def _collect_metrics(self) -> dict[str, HwMetric]:
        # We lazily collect all metrics so that the metrics manager can be
        # constructed at any time. Otherwise, if a metric object was created
        # after the manager object had been created, that metric wouldn't end up
        # being registered.
        metrics: dict[str, HwMetric] = {}
        for metric in DependencyContext.get().get_dependency(HwMetricsListKey()):
            if metric.fully_qualified_name in metrics:
                raise RuntimeError(f"Metric '{metric.fully_qualified_name}' is already registered")

            metrics[metric.fully_qualified_name] = metric

        return metrics

    def get_metrics(self) -> dict[str, HwMetric]:
        """
        Returns all metrics registered in the circuit.
        """
        if self._metrics is None:
            self._metrics = self._collect_metrics()
        return self._metrics

    def get_register_value(self, metric_name: str, reg_name: str) -> Signal:
        """
        Returns the signal holding the register value of the given metric.

        Parameters
        ----------
        metric_name: str
            The fully qualified name of the metric, for example 'frontend.icache.loads'.
        reg_name: str
            The name of the register from that metric, for example if
            the metric is a histogram, the 'reg_name' could be 'min'
            or 'bucket-32'.
        """

        metrics = self.get_metrics()
        if metric_name not in metrics:
            raise RuntimeError(f"Couldn't find metric '{metric_name}'")
        return metrics[metric_name].signals[reg_name]

    def debug_signals(self) -> SignalBundle:
        """
        Returns tree-like SignalBundle composed of all metric registers.
        """
        metrics = self.get_metrics()

        def rec(metric_names: list[str], depth: int = 1):
            bundle: list[SignalBundle] = []
            components: dict[str, list[str]] = {}

            for metric in metric_names:
                parts = metric.split(".")

                if len(parts) == depth:
                    signals = metrics[metric].signals
                    reg_values = [signals[reg_name] for reg_name in signals]

                    bundle.append({metric: reg_values})

                    continue

                component_prefix = ".".join(parts[:depth])

                if component_prefix not in components:
                    components[component_prefix] = []
                components[component_prefix].append(metric)

            for component_name, elements in components.items():
                bundle.append({component_name: rec(elements, depth + 1)})

            return bundle

        return {"metrics": rec(list(self.get_metrics().keys()))}
