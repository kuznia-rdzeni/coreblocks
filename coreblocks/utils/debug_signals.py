from amaranth import *
from ._typing import DebugSignals


class AutoDebugSignals:
    def debug_signals(self) -> DebugSignals:
        slist: list[DebugSignals] = []
        smap: dict[str, DebugSignals] = {}

        for v in vars(self):
            a = getattr(self, v)
            if hasattr(a, "debug_signals"):
                smap[v] = a.debug_signals()
            elif isinstance(a, Signal) or isinstance(a, Record):
                slist.append(a)

        slist.append(smap)
        return slist
