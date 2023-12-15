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
