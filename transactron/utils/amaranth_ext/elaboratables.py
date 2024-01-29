import itertools
from contextlib import contextmanager
from typing import Literal, Optional, overload
from collections.abc import Iterable
from amaranth import *
from transactron.utils._typing import HasElaborate, ModuleLike

__all__ = [
    "OneHotSwitchDynamic",
    "OneHotSwitch",
    "ModuleConnector",
    "Scheduler",
    "RoundRobin",
    "MultiPriorityEncoder",
]


@contextmanager
def OneHotSwitch(m: ModuleLike, test: Value):
    """One-hot switch.

    This function allows one-hot matching in the style similar to the standard
    Amaranth `Switch`. This allows to get the performance benefit of using
    the one-hot representation.

    Example::

        with OneHotSwitch(m, sig) as OneHotCase:
            with OneHotCase(0b01):
                ...
            with OneHotCase(0b10):
                ...
            # optional default case
            with OneHotCase():
                ...

    Parameters
    ----------
    m : Module
        The module for which the matching is defined.
    test : Signal
        The signal being tested.
    """

    @contextmanager
    def case(n: Optional[int] = None):
        if n is None:
            with m.Case():
                yield
        else:
            # find the index of the least significant bit set
            i = (n & -n).bit_length() - 1
            if n - (1 << i) != 0:
                raise ValueError("%d not in one-hot representation" % n)
            with m.Case(n):
                yield

    with m.Switch(test):
        yield case


@overload
def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: Literal[True]) -> Iterable[Optional[int]]:
    ...


@overload
def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: Literal[False] = False) -> Iterable[int]:
    ...


def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: bool = False) -> Iterable[Optional[int]]:
    """Dynamic one-hot switch.

    This function allows simple one-hot matching on signals which can have
    variable bit widths.

    Example::

        for i in OneHotSwitchDynamic(m, sig):
            # code dependent on the bit index i
            ...

    Parameters
    ----------
    m : Module
        The module for which the matching is defined.
    test : Signal
        The signal being tested.
    default : bool, optional
        Whether the matching includes a default case (signified by a None).
    """
    count = len(test)
    with OneHotSwitch(m, test) as OneHotCase:
        for i in range(count):
            with OneHotCase(1 << i):
                yield i
        if default:
            with OneHotCase():
                yield None
    return


class ModuleConnector(Elaboratable):
    """
    An Elaboratable to create a new module, which will have all arguments
    added as its submodules.
    """

    def __init__(self, *args: HasElaborate, **kwargs: HasElaborate):
        """
        Parameters
        ----------
        *args
            Modules which should be added as anonymous submodules.
        **kwargs
            Modules which will be added as named submodules.
        """
        self.args = args
        self.kwargs = kwargs

    def elaborate(self, platform):
        m = Module()

        for elem in self.args:
            m.submodules += elem

        for name, elem in self.kwargs.items():
            m.submodules[name] = elem

        return m


class Scheduler(Elaboratable):
    """Scheduler

    An implementation of a round-robin scheduler, which is used in the
    transaction subsystem. It is based on Amaranth's round-robin scheduler
    but instead of using binary numbers, it uses one-hot encoding for the
    `grant` output signal.

    Attributes
    ----------
    requests: Signal(count), in
        Signals that something (e.g. a transaction) wants to run. When i-th
        bit is high, then the i-th agent requests the grant signal.
    grant: Signal(count), out
        Signals that something (e.g. transaction) is granted to run. It uses
        one-hot encoding.
    valid : Signal(1), out
        Signal that `grant` signals are valid.
    """

    def __init__(self, count: int):
        """
        Parameters
        ----------
        count : int
            Number of agents between which the scheduler should arbitrate.
        """
        if not isinstance(count, int) or count < 0:
            raise ValueError("Count must be a non-negative integer, not {!r}".format(count))
        self.count = count

        self.requests = Signal(count)
        self.grant = Signal(count, reset=1)
        self.valid = Signal()

    def elaborate(self, platform):
        m = Module()

        grant_reg = Signal.like(self.grant)

        for i in OneHotSwitchDynamic(m, grant_reg, default=True):
            if i is not None:
                m.d.comb += self.grant.eq(grant_reg)
                for j in itertools.chain(reversed(range(i)), reversed(range(i + 1, self.count))):
                    with m.If(self.requests[j]):
                        m.d.comb += self.grant.eq(1 << j)
            else:
                m.d.comb += self.grant.eq(0)

        m.d.comb += self.valid.eq(self.requests.any())

        m.d.sync += grant_reg.eq(self.grant)

        return m


class RoundRobin(Elaboratable):
    """Round-robin scheduler.
    For a given set of requests, the round-robin scheduler will
    grant one request. Once it grants a request, if any other
    requests are active, it grants the next active request with
    a greater number, restarting from zero once it reaches the
    highest one.
    Use :class:`EnableInserter` to control when the scheduler
    is updated.

    Implementation ported from amaranth lib.

    Parameters
    ----------
    count : int
        Number of requests.
    Attributes
    ----------
    requests : Signal(count), in
        Set of requests.
    grant : Signal(range(count)), out
        Number of the granted request. Does not change if there are no
        active requests.
    valid : Signal(), out
        Asserted if grant corresponds to an active request. Deasserted
        otherwise, i.e. if no requests are active.
    """

    def __init__(self, *, count):
        if not isinstance(count, int) or count < 0:
            raise ValueError("Count must be a non-negative integer, not {!r}".format(count))
        self.count = count

        self.requests = Signal(count)
        self.grant = Signal(range(count))
        self.valid = Signal()

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.grant):
            for i in range(self.count):
                with m.Case(i):
                    for pred in reversed(range(i)):
                        with m.If(self.requests[pred]):
                            m.d.sync += self.grant.eq(pred)
                    for succ in reversed(range(i + 1, self.count)):
                        with m.If(self.requests[succ]):
                            m.d.sync += self.grant.eq(succ)

        m.d.sync += self.valid.eq(self.requests.any())

        return m


class MultiPriorityEncoder(Elaboratable):
    """Priority encoder with more outputs

    This is an extension of the `PriorityEncoder` from amaranth, that supports
    generating more than one output from an input signal. In other words
    it decodes multi-hot encoded signal to lists of signals in binary
    format, each with index of a different high bit in input.

    Attributes
    ----------
    input_width : int
        Width of the input signal
    outputs_count : int
        Number of outputs to generate at once.
    input : Signal, in
        Signal with 1 on `i`-th bit if `i` can be selected by encoder
    outputs : list[Signal], out
        Signals with selected indicies, they are sorted in ascending order,
        if the number of ready signals is less than `outputs_count`,
        then valid signals are at the beginning of the list.
    valids : list[Signals], out
        One bit for each output signal, indicating whether the output is valid or not.
    """

    def __init__(self, input_width: int, outputs_count: int):
        self.input_width = input_width
        self.outputs_count = outputs_count

        self.input = Signal(self.input_width)
        self.outputs = [Signal(range(self.input_width), name="output") for _ in range(self.outputs_count)]
        self.valids = [Signal(name="valid") for _ in range(self.outputs_count)]

    def elaborate(self, platform):
        m = Module()

        current_outputs = [Signal(range(self.input_width)) for _ in range(self.outputs_count)]
        current_valids = [Signal() for _ in range(self.outputs_count)]
        for j in reversed(range(self.input_width)):
            new_current_outputs = [Signal(range(self.input_width)) for _ in range(self.outputs_count)]
            new_current_valids = [Signal() for _ in range(self.outputs_count)]
            with m.If(self.input[j]):
                m.d.comb += new_current_outputs[0].eq(j)
                m.d.comb += new_current_valids[0].eq(1)
                for k in range(self.outputs_count - 1):
                    m.d.comb += new_current_outputs[k + 1].eq(current_outputs[k])
                    m.d.comb += new_current_valids[k + 1].eq(current_valids[k])
            with m.Else():
                for k in range(self.outputs_count):
                    m.d.comb += new_current_outputs[k].eq(current_outputs[k])
                    m.d.comb += new_current_valids[k].eq(current_valids[k])
            current_outputs = new_current_outputs
            current_valids = new_current_valids

        for k in range(self.outputs_count):
            m.d.comb += self.outputs[k].eq(current_outputs[k])
            m.d.comb += self.valids[k].eq(current_valids[k])

        return m
