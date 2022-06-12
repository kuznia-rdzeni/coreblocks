from contextlib import contextmanager
import itertools
from typing import Iterable, TypeAlias, TypeVar, Mapping
from amaranth import *
from .._typing import LayoutLike

__all__ = ["Scheduler", "_graph_ccs", "MethodLayout", "_coerce_layout", "ROGraph", "Graph", "GraphCC", "OneHotSwitch"]


T = TypeVar("T")


def OneHotSwitch(m, in_signal: Signal, *, default=False):
    count = len(in_signal)
    with m.Switch(in_signal):
        for i in range(count):
            with m.Case("-" * (count - i - 1) + "1" + "-" * i):
                yield i
        yield -1
    return


class Scheduler(Elaboratable):
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

        for i in OneHotSwitch(m, grant_reg, default=True):
            if i >= 0:
                m.d.comb += self.grant.eq(grant_reg)
                for j in itertools.chain(reversed(range(i)), reversed(range(i + 1, self.count))):
                    with m.If(self.requests[j]):
                        m.d.comb += self.grant.eq(1 << j)
            else:
                with m.Case():
                    m.d.comb += self.grant.eq(0)

        m.d.comb += self.valid.eq(self.requests.any())

        m.d.sync += grant_reg.eq(self.grant)

        return m


ROGraph: TypeAlias = Mapping[T, Iterable[T]]
Graph: TypeAlias = dict[T, set[T]]
GraphCC: TypeAlias = set[T]


def _graph_ccs(gr: ROGraph[T]) -> list[GraphCC[T]]:
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
