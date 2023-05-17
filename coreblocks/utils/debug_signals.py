from amaranth import *
from ._typing import SignalBundle, HasDebugSignals
from collections.abc import Collection, Mapping
import coreblocks.transactions.core


def auto_debug_signals(thing) -> SignalBundle:
    """Automatic debug signal generation.

    Exposes class attributes with debug signals (Amaranth `Signal`\\s,
    `Record`\\s, `Array`\\s and `Elaboratable`\\s, `Method`\\s, classes
    which define `debug_signals`). Used for generating ``gtkw`` files in
    tests, for use in ``gtkwave``.
    """

    def auto_debug_signals_internal(thing, *, _visited: set) -> SignalBundle:
        # Please note, that the set `_visited` is used to memorise visited elements
        # to break reference cycles. There is only one instance of this set, for whole
        # `auto_debug_signals` recursion stack. It is being mutated by adding to it more
        # elements id, so that caller know what was visited by callee.
        slist: list[SignalBundle] = []
        smap: dict[str, SignalBundle] = {}

        if isinstance(thing, HasDebugSignals):
            return thing.debug_signals()

        try:
            vs = vars(thing)
        except (KeyError, AttributeError, TypeError):
            return []

        _visited.add(id(thing))

        for v in vs:
            a = getattr(thing, v)
            if v == "func_block_unifier":
                print(v)

            # ignore private fields (mostly to ignore _MustUse_context to get pretty print)
            if v[0] == "_":
                continue

            # Check for reference cycles e.g. Amaranth's MustUse
            if id(a) in _visited:
                continue
            _visited.add(id(a))

            match a:
                case Elaboratable() | coreblocks.transactions.core.TransactionBase():
                    smap[v] = auto_debug_signals_internal(a, _visited=_visited)
                case Array():
                    for i, e in enumerate(a):
                        if isinstance(e, Record):
                            e.name = f"{v}[{i}]"
                    smap[v] = a
                case Signal() | Record():
                    slist.append(a)
                case Mapping():
                    submap = {}
                    for i, e in a.items():
                        sublist = auto_debug_signals_internal(e, _visited=_visited)
                        if sublist:
                            submap[f"{v}[{i}]"] = sublist
                    if submap:
                        smap[v] = submap
                # avoid infinite recursion (strings are `Collection`s of strings)
                case str():
                    continue
                case Collection():
                    submap = {}
                    for i, e in enumerate(a):
                        sublist = auto_debug_signals_internal(e, _visited=_visited)
                        if sublist:
                            submap[f"{v}[{i}]"] = sublist
                    if submap:
                        smap[v] = submap

        slist.append(smap)
        return slist

    lst =auto_debug_signals_internal(thing, _visited=set())
    return lst
