import itertools
from contextlib import contextmanager
from typing import Literal, Optional, overload
from collections.abc import Iterable
from amaranth import *
from transactron.utils._typing import HasElaborate, ModuleLike, ValueLike

__all__ = [
    "OneHotSwitchDynamic",
    "OneHotSwitch",
    "ModuleConnector",
    "Scheduler",
    "RoundRobin",
    "MultiPriorityEncoder",
    "RingMultiPriorityEncoder",
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
            with m.Default():
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
def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: Literal[True]) -> Iterable[Optional[int]]: ...


@overload
def OneHotSwitchDynamic(m: ModuleLike, test: Value, *, default: Literal[False] = False) -> Iterable[int]: ...


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

    This is an extension of the `PriorityEncoder` from amaranth that supports
    more than one output from an input signal. In other words
    it decodes multi-hot encoded signal into lists of signals in binary
    format, each with the index of a different high bit in the input.

    Attributes
    ----------
    input_width : int
        Width of the input signal
    outputs_count : int
        Number of outputs to generate at once.
    input : Signal, in
        Signal with 1 on `i`-th bit if `i` can be selected by encoder
    outputs : list[Signal], out
        Signals with selected indicies, sorted in ascending order,
        if the number of ready signals is less than `outputs_count`
        then valid signals are at the beginning of the list.
    valids : list[Signal], out
        One bit for each output signal, indicating whether the output is valid or not.
    """

    def __init__(self, input_width: int, outputs_count: int):
        self.input_width = input_width
        self.outputs_count = outputs_count

        self.input = Signal(self.input_width)
        self.outputs = [Signal(range(self.input_width), name=f"output_{i}") for i in range(self.outputs_count)]
        self.valids = [Signal(name=f"valid_{i}") for i in range(self.outputs_count)]

    @staticmethod
    def create(
        m: Module, input_width: int, input: ValueLike, outputs_count: int = 1, name: Optional[str] = None
    ) -> list[tuple[Signal, Signal]]:
        """Syntax sugar for creating MultiPriorityEncoder

        This static method allows to use MultiPriorityEncoder in a more functional
        way. Instead of creating the instance manually, connecting all the signals and
        adding a submodule, you can call this function to do it automatically.

        This function is equivalent to:

        .. highlight:: python
        .. code-block:: python

            m.submodules += prio_encoder = PriorityEncoder(cnt)
            m.d.top_comb += prio_encoder.input.eq(one_hot_singal)
            idx = prio_encoder.outputs
            valid = prio.encoder.valids

        Parameters
        ----------
        m: Module
            Module to add the MultiPriorityEncoder to.
        input_width : int
            Width of the one hot signal.
        input : ValueLike
            The one hot signal to decode.
        outputs_count : int
            Number of different decoder outputs to generate at once. Default: 1.
        name : Optional[str]
            Name to use when adding MultiPriorityEncoder to submodules.
            If None, it will be added as an anonymous submodule. The given name
            can not be used in a submodule that has already been added. Default: None.

        Returns
        -------
        return : list[tuple[Signal, Signal]]
            Returns a list with len equal to outputs_count. Each tuple contains
            a pair of decoded index on the first position and a valid signal
            on the second position.
        """
        prio_encoder = MultiPriorityEncoder(input_width, outputs_count)
        if name is None:
            m.submodules += prio_encoder
        else:
            try:
                getattr(m.submodules, name)
                raise ValueError(f"Name: {name} is already in use, so MultiPriorityEncoder can not be added with it.")
            except AttributeError:
                setattr(m.submodules, name, prio_encoder)
        m.d.top_comb += prio_encoder.input.eq(input)
        return list(zip(prio_encoder.outputs, prio_encoder.valids))

    @staticmethod
    def create_simple(
        m: Module, input_width: int, input: ValueLike, name: Optional[str] = None
    ) -> tuple[Signal, Signal]:
        """Syntax sugar for creating MultiPriorityEncoder

        This is the same as `create` function, but with `outputs_count` hardcoded to 1.
        """
        lst = MultiPriorityEncoder.create(m, input_width, input, outputs_count=1, name=name)
        return lst[0]

    def build_tree(self, m: Module, in_sig: Signal, start_idx: int):
        assert len(in_sig) > 0
        level_outputs = [
            Signal(range(self.input_width), name=f"_lvl_out_idx{start_idx}_{i}") for i in range(self.outputs_count)
        ]
        level_valids = [Signal(name=f"_lvl_val_idx{start_idx}_{i}") for i in range(self.outputs_count)]
        if len(in_sig) == 1:
            with m.If(in_sig):
                m.d.comb += level_outputs[0].eq(start_idx)
                m.d.comb += level_valids[0].eq(1)
        else:
            middle = len(in_sig) // 2
            r_in = Signal(middle, name=f"_r_in_idx{start_idx}")
            l_in = Signal(len(in_sig) - middle, name=f"_l_in_idx{start_idx}")
            m.d.comb += r_in.eq(in_sig[0:middle])
            m.d.comb += l_in.eq(in_sig[middle:])
            r_out, r_val = self.build_tree(m, r_in, start_idx)
            l_out, l_val = self.build_tree(m, l_in, start_idx + middle)

            with m.Switch(Cat(r_val)):
                for i in range(self.outputs_count + 1):
                    with m.Case((1 << i) - 1):
                        for j in range(i):
                            m.d.comb += level_outputs[j].eq(r_out[j])
                            m.d.comb += level_valids[j].eq(r_val[j])
                        for j in range(i, self.outputs_count):
                            m.d.comb += level_outputs[j].eq(l_out[j - i])
                            m.d.comb += level_valids[j].eq(l_val[j - i])
        return level_outputs, level_valids

    def elaborate(self, platform):
        m = Module()

        level_outputs, level_valids = self.build_tree(m, self.input, 0)

        for k in range(self.outputs_count):
            m.d.comb += self.outputs[k].eq(level_outputs[k])
            m.d.comb += self.valids[k].eq(level_valids[k])

        return m


class RingMultiPriorityEncoder(Elaboratable):
    """Priority encoder with one or more outputs and flexible start

    This is an extension of the `MultiPriorityEncoder` that supports
    flexible start and end indexes. In the standard `MultiPriorityEncoder`
    the first bit is always at position 0 and the last is the last bit of
    the input signal. In this extended implementation, both can be
    selected at runtime.

    This implementation is intended for selection from the circular buffers,
    so if `last < first` the encoder will first select bits from
    [first, input_width) and then from [0, last).

    Attributes
    ----------
    input_width : int
        Width of the input signal
    outputs_count : int
        Number of outputs to generate at once.
    input : Signal, in
        Signal with 1 on `i`-th bit if `i` can be selected by encoder
    first : Signal, in
        Index of the first bit in the `input`. Inclusive.
    last : Signal, out
        Index of the last bit in the `input`. Exclusive.
    outputs : list[Signal], out
        Signals with selected indicies, sorted in ascending order,
        if the number of ready signals is less than `outputs_count`
        then valid signals are at the beginning of the list.
    valids : list[Signal], out
        One bit for each output signal, indicating whether the output is valid or not.
    """

    def __init__(self, input_width: int, outputs_count: int):
        self.input_width = input_width
        self.outputs_count = outputs_count

        self.input = Signal(self.input_width)
        self.first = Signal(range(self.input_width))
        self.last = Signal(range(self.input_width))
        self.outputs = [Signal(range(self.input_width), name=f"output_{i}") for i in range(self.outputs_count)]
        self.valids = [Signal(name=f"valid_{i}") for i in range(self.outputs_count)]

    @staticmethod
    def create(
        m: Module,
        input_width: int,
        input: ValueLike,
        first: ValueLike,
        last: ValueLike,
        outputs_count: int = 1,
        name: Optional[str] = None,
    ) -> list[tuple[Signal, Signal]]:
        """Syntax sugar for creating RingMultiPriorityEncoder

        This static method allows to use RingMultiPriorityEncoder in a more functional
        way. Instead of creating the instance manually, connecting all the signals and
        adding a submodule, you can call this function to do it automatically.

        This function is equivalent to:

        .. highlight:: python
        .. code-block:: python

            m.submodules += prio_encoder = RingMultiPriorityEncoder(input_width, outputs_count)
            m.d.comb += prio_encoder.input.eq(one_hot_singal)
            m.d.comb += prio_encoder.first.eq(first)
            m.d.comb += prio_encoder.last.eq(last)
            idx = prio_encoder.outputs
            valid = prio.encoder.valids

        Parameters
        ----------
        m: Module
            Module to add the RingMultiPriorityEncoder to.
        input_width : int
            Width of the one hot signal.
        input : ValueLike
            The one hot signal to decode.
        first : ValueLike
            Index of the first bit in the `input`. Inclusive.
        last : ValueLike
            Index of the last bit in the `input`. Exclusive.
        outputs_count : int
            Number of different decoder outputs to generate at once. Default: 1.
        name : Optional[str]
            Name to use when adding RingMultiPriorityEncoder to submodules.
            If None, it will be added as an anonymous submodule. The given name
            can not be used in a submodule that has already been added. Default: None.

        Returns
        -------
        return : list[tuple[Signal, Signal]]
            Returns a list with len equal to outputs_count. Each tuple contains
            a pair of decoded index on the first position and a valid signal
            on the second position.
        """
        prio_encoder = RingMultiPriorityEncoder(input_width, outputs_count)
        if name is None:
            m.submodules += prio_encoder
        else:
            try:
                getattr(m.submodules, name)
                raise ValueError(
                    f"Name: {name} is already in use, so RingMultiPriorityEncoder can not be added with it."
                )
            except AttributeError:
                setattr(m.submodules, name, prio_encoder)
        m.d.comb += prio_encoder.input.eq(input)
        m.d.comb += prio_encoder.first.eq(first)
        m.d.comb += prio_encoder.last.eq(last)
        return list(zip(prio_encoder.outputs, prio_encoder.valids))

    @staticmethod
    def create_simple(
        m: Module, input_width: int, input: ValueLike, first: ValueLike, last: ValueLike, name: Optional[str] = None
    ) -> tuple[Signal, Signal]:
        """Syntax sugar for creating RingMultiPriorityEncoder

        This is the same as `create` function, but with `outputs_count` hardcoded to 1.
        """
        lst = RingMultiPriorityEncoder.create(m, input_width, input, first, last, outputs_count=1, name=name)
        return lst[0]

    def elaborate(self, platform):
        m = Module()
        double_input = Signal(2 * self.input_width)
        m.d.comb += double_input.eq(Cat(self.input, self.input))

        last_corrected = Signal(range(self.input_width * 2))
        with m.If(self.first > self.last):
            m.d.comb += last_corrected.eq(self.input_width + self.last)
        with m.Else():
            m.d.comb += last_corrected.eq(self.last)

        mask = Signal.like(double_input)
        m.d.comb += mask.eq((1 << last_corrected) - 1)

        multi_enc_input = (double_input & mask) >> self.first

        m.submodules.multi_enc = multi_enc = MultiPriorityEncoder(self.input_width, self.outputs_count)
        m.d.comb += multi_enc.input.eq(multi_enc_input)
        for k in range(self.outputs_count):
            moved_out = Signal(range(2 * self.input_width))
            m.d.comb += moved_out.eq(multi_enc.outputs[k] + self.first)
            corrected_out = Mux(moved_out >= self.input_width, moved_out - self.input_width, moved_out)

            m.d.comb += self.outputs[k].eq(corrected_out)
            m.d.comb += self.valids[k].eq(multi_enc.valids[k])
        return m
