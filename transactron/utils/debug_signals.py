from typing import Optional
from amaranth import *
from ._typing import SignalBundle, HasDebugSignals
from collections.abc import Collection, Mapping


def auto_debug_signals(thing) -> SignalBundle:
    """Automatic debug signal generation.

    Exposes class attributes with debug signals (Amaranth `Signal`\\s,
    `Record`\\s, `Array`\\s and `Elaboratable`\\s, `Method`\\s, classes
    which define `debug_signals`). Used for generating ``gtkw`` files in
    tests, for use in ``gtkwave``.
    """

    def auto_debug_signals_internal(thing, *, _visited: set) -> Optional[SignalBundle]:
        # Please note, that the set `_visited` is used to memorise visited elements
        # to break reference cycles. There is only one instance of this set, for whole
        # `auto_debug_signals` recursion stack. It is being mutated by adding to it more
        # elements id, so that caller know what was visited by callee.
        smap: dict[str, SignalBundle] = {}

        # Check for reference cycles e.g. Amaranth's MustUse
        if id(thing) in _visited:
            return None
        _visited.add(id(thing))

        match thing:
            case HasDebugSignals():
                return thing.debug_signals()
            # avoid infinite recursion (strings are `Collection`s of strings)
            case str():
                return None
            case Collection() | Mapping():
                match thing:
                    case Collection():
                        f_iter = enumerate(thing)
                    case Mapping():
                        f_iter = thing.items()
                for i, e in f_iter:
                    sublist = auto_debug_signals_internal(e, _visited=_visited)
                    if sublist is not None:
                        smap[f"[{i}]"] = sublist
                if smap:
                    return smap
                return None
            case Array():
                for i, e in enumerate(thing):
                    if isinstance(e, Record):
                        e.name = f"[{i}]"
                return thing
            case Signal() | Record():
                return thing
            case _:
                try:
                    vs = vars(thing)
                except (KeyError, AttributeError, TypeError):
                    return None

                for v in vs:
                    a = getattr(thing, v)

                    # ignore private fields (mostly to ignore _MustUse_context to get pretty print)
                    if v[0] == "_":
                        continue

                    dsignals = auto_debug_signals_internal(a, _visited=_visited)
                    if dsignals is not None:
                        smap[v] = dsignals
                if smap:
                    return smap
                return None

    ret = auto_debug_signals_internal(thing, _visited=set())
    if ret is None:
        return []
    return ret
