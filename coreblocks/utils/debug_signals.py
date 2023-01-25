from amaranth import *
from ._typing import DebugSignals


def auto_debug_signals(thing) -> DebugSignals:
    """Automatic debug signal generation.

    Exposes class attributes with debug signals (Amaranth `Signal`\\s and
    `Record`\\s, `Elaboratable`\\s, `Method`\\s, classes which define
    `debug_signals`). Used for generating ``gtkw`` files in tests,
    for use in ``gtkwave``.
    """

    slist: list[DebugSignals] = []
    smap: dict[str, DebugSignals] = {}

    for v in vars(thing):
        a = getattr(thing, v)
        if hasattr(a, "debug_signals"):
            smap[v] = a.debug_signals()
        elif isinstance(a, Elaboratable):
            smap[v] = auto_debug_signals(a)
        elif isinstance(a, Array):
            for i, e in enumerate(a):
                if isinstance(e, Record):
                    e.name = f"{v}[{i}]"
            smap[v] = a
        elif isinstance(a, Signal) or isinstance(a, Record):
            slist.append(a)

    slist.append(smap)
    return slist
