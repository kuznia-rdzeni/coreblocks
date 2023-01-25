from amaranth import *
from ._typing import DebugSignals, HasDebugSignals


class AutoDebugSignals:
    """Mixin for automatic debug signal generation.

    Should be mixed in to `Elaboratable`\\s. Adds a method `debug_signals`,
    which exposes class attributes with debug signals (Amaranth `Signal`\\s
    and `Record`\\s, `Method`\\s, and other classes which define
    `debug_signals`). Used for generating ``gtkw`` files in tests,
    for use in ``gtkwave``.
    """

    def debug_signals(self) -> DebugSignals:
        slist: list[DebugSignals] = []
        smap: dict[str, DebugSignals] = {}

        for v in vars(self):
            a = getattr(self, v)
            if isinstance(a, HasDebugSignals):
                smap[v] = a.debug_signals()
            elif isinstance(a, Signal) or isinstance(a, Record):
                slist.append(a)

        slist.append(smap)
        return slist
