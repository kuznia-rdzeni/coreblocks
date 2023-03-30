from amaranth import *
from ._typing import SignalBundle, HasDebugSignals


def auto_debug_signals(thing) -> SignalBundle:
    """Automatic debug signal generation.

    Exposes class attributes with debug signals (Amaranth `Signal`\\s,
    `Record`\\s, `Array`\\s and `Elaboratable`\\s, `Method`\\s, classes
    which define `debug_signals`). Used for generating ``gtkw`` files in
    tests, for use in ``gtkwave``.
    """

    slist: list[SignalBundle] = []
    smap: dict[str, SignalBundle] = {}

    if "__dict__" not in dir(thing):
        return []

    for v in vars(thing):
        a = getattr(thing, v)
        if isinstance(a, HasDebugSignals):
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
        elif isinstance(a, list):
            submap={}
            for i, e in enumerate(a):
                if isinstance(e, HasDebugSignals):
                    e.name = f"{v}[{i}]"
                    submap[e.name] = e.debug_signals()
                else:
                    sublist = auto_debug_signals(e)
                    if sublist:
                        submap[f"{v}[{i}]"] = sublist
            if submap:
                smap[v]=submap

    slist.append(smap)
    return slist
