import itertools
import sys
from inspect import Parameter, signature
from typing import Any, Concatenate, Optional, TypeAlias, TypeGuard, TypeVar
from collections.abc import Callable, Iterable, Mapping
from amaranth import *
from transactron.utils._typing import LayoutLike, ShapeLike
from transactron.utils import OneHotSwitchDynamic

__all__ = [
    "Scheduler",
    "_graph_ccs",
    "MethodLayout",
    "ROGraph",
    "Graph",
    "GraphCC",
    "get_caller_class_name",
    "def_helper",
    "method_def_helper",
]


T = TypeVar("T")
U = TypeVar("U")


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


ROGraph: TypeAlias = Mapping[T, Iterable[T]]
Graph: TypeAlias = dict[T, set[T]]
GraphCC: TypeAlias = set[T]


def _graph_ccs(gr: ROGraph[T]) -> list[GraphCC[T]]:
    """_graph_ccs

    Find connected components in a graph.

    Parameters
    ----------
    gr : Mapping[T, Iterable[T]]
        Graph in which we should find connected components. Encoded using
        adjacency lists.

    Returns
    -------
    ccs : List[Set[T]]
        Connected components of the graph `gr`.
    """
    ccs = []
    cc = set()
    visited = set()

    for v in gr.keys():
        q = [v]
        while q:
            w = q.pop()
            if w in visited:
                continue
            visited.add(w)
            cc.add(w)
            q.extend(gr[w])
        if cc:
            ccs.append(cc)
            cc = set()

    return ccs


MethodLayout: TypeAlias = LayoutLike


def has_first_param(func: Callable[..., T], name: str, tp: type[U]) -> TypeGuard[Callable[Concatenate[U, ...], T]]:
    parameters = signature(func).parameters
    return (
        len(parameters) >= 1
        and next(iter(parameters)) == name
        and parameters[name].kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY}
        and parameters[name].annotation in {Parameter.empty, tp}
    )


def def_helper(description, func: Callable[..., T], tp: type[U], arg: U, /, **kwargs) -> T:
    parameters = signature(func).parameters
    kw_parameters = set(
        n for n, p in parameters.items() if p.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}
    )
    if len(parameters) == 1 and has_first_param(func, "arg", tp):
        return func(arg)
    elif kw_parameters <= kwargs.keys():
        return func(**kwargs)
    else:
        raise TypeError(f"Invalid {description}: {func}")


def mock_def_helper(tb, func: Callable[..., T], arg: Mapping[str, Any]) -> T:
    return def_helper(f"mock definition for {tb}", func, Mapping[str, Any], arg, **arg)


def method_def_helper(method, func: Callable[..., T], arg: Record) -> T:
    return def_helper(f"method definition for {method}", func, Record, arg, **arg.fields)


def get_caller_class_name(default: Optional[str] = None) -> tuple[Optional[Elaboratable], str]:
    caller_frame = sys._getframe(2)
    if "self" in caller_frame.f_locals:
        owner = caller_frame.f_locals["self"]
        return owner, owner.__class__.__name__
    elif default is not None:
        return None, default
    else:
        raise RuntimeError("Not called from a method")


def data_layout(val: ShapeLike) -> LayoutLike:
    return [("data", val)]


def neg(x: int, xlen: int) -> int:
    """
    Computes the negation of a number in the U2 system.

    Parameters
    ----------
    x: int
        Number in U2 system.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Negation of x in the U2 system.
    """
    return (-x) & (2**xlen - 1)


def int_to_signed(x: int, xlen: int) -> int:
    """
    Converts a Python integer into its U2 representation.

    Parameters
    ----------
    x: int
        Signed Python integer.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Representation of x in the U2 system.
    """
    return x & (2**xlen - 1)


def signed_to_int(x: int, xlen: int) -> int:
    """
    Changes U2 representation into Python integer

    Parameters
    ----------
    x: int
        Number in U2 system.
    xlen : int
        Bit width of x.

    Returns
    -------
    return : int
        Representation of x as signed Python integer.
    """
    return x | -(x & (2 ** (xlen - 1)))
