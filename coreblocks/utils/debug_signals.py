from amaranth import *
from ._typing import SignalBundle, HasDebugSignals
from collections.abc import Collection, Mapping
import coreblocks.transactions.core


def auto_debug_signals(thing, *, visited: set = set()) -> SignalBundle:
    """Automatic debug signal generation.

    Exposes class attributes with debug signals (Amaranth `Signal`\\s,
    `Record`\\s, `Array`\\s and `Elaboratable`\\s, `Method`\\s, classes
    which define `debug_signals`). Used for generating ``gtkw`` files in
    tests, for use in ``gtkwave``.
    """

    slist: list[SignalBundle] = []
    smap: dict[str, SignalBundle] = {}

    if isinstance(thing, HasDebugSignals):
        return thing.debug_signals()

    if "__dict__" not in dir(thing):
        return []

    visited.add(id(thing))

    for v in vars(thing):
        a = getattr(thing, v)

        # Check for reference cycles e.g. Amaranth's MustUse
        if id(a) in visited:
            continue
        visited.add(id(a))

        # ignore private fields (mostly to ignore _MustUse_context to get preaty print)
        if v[0] == "_":
            continue

        if isinstance(a, Elaboratable) or isinstance(a, coreblocks.transactions.core.TransactionBase):
            smap[v] = auto_debug_signals(a, visited=visited)
        elif isinstance(a, Array):
            for i, e in enumerate(a):
                if isinstance(e, Record):
                    e.name = f"{v}[{i}]"
            smap[v] = a
        elif isinstance(a, Signal) or isinstance(a, Record):
            slist.append(a)
        elif isinstance(a, Mapping):
            submap = {}
            for i, e in a.items():
                sublist = auto_debug_signals(e, visited=visited)
                if sublist:
                    submap[f"{v}[{i}]"] = sublist
            if submap:
                smap[v] = submap
        elif isinstance(a, Collection):
            submap = {}
            for i, e in enumerate(a):
                sublist = auto_debug_signals(e, visited=visited)
                if sublist:
                    submap[f"{v}[{i}]"] = sublist
            if submap:
                smap[v] = submap

    slist.append(smap)
    return slist
