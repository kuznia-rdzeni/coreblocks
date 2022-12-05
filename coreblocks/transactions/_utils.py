import itertools
import sys
from typing import Iterable, Optional, TypeAlias, TypeVar, Mapping
from amaranth import *
from ..utils._typing import LayoutLike
from coreblocks.utils import OneHotSwitchDynamic

__all__ = [
    "Scheduler",
    "_graph_ccs",
    "MethodLayout",
    "_coerce_layout",
    "ROGraph",
    "Graph",
    "GraphCC",
    "get_caller_class_name",
]


T = TypeVar("T")


class Scheduler(Elaboratable):
    """Scheduler

    An implementation of a round-robin scheduler, which is used in the
    transaction subsystem. It is based on Amaranth's round-robin scheduler
    but instead of using binary numbers, it uses one-hot encoding for the
    ``grant`` output signal.

    Parameters
    ----------
    count : int
        Number of agents between which the scheduler should arbitrate.

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


MethodLayout = int | LayoutLike


def _coerce_layout(int_or_layout: MethodLayout) -> LayoutLike:
    if isinstance(int_or_layout, int):
        return [("data", int_or_layout)]
    else:
        return int_or_layout


def get_caller_class_name(default: Optional[str] = None) -> tuple[Optional[Elaboratable], str]:
    caller_frame = sys._getframe(2)
    if "self" in caller_frame.f_locals:
        owner = caller_frame.f_locals["self"]
        return owner, owner.__class__.__name__
    elif default is not None:
        return None, default
    else:
        raise RuntimeError("Not called from a method")
