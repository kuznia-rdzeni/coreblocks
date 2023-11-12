from functools import reduce
from amaranth import *

from coreblocks.params import *
from coreblocks.utils import HasElaborate
from transactron.core import Method, def_method, TModule


class PhysMemAttr(Elaboratable):
    """
    Implementation of singular physical memory attribute.
    `PhysMemAttr` should be embedded into PMAChecker.

    Attributes
    ----------
    in_addr : Signal, in
        Instructs to return attribute of particular memory address.
    out : Signal, out
        Response to inquiry about atribute of `in_addr` memory address.
    """

    @staticmethod
    def merge_intervals(acc: tuple[tuple[int, int], list], el: tuple[int, int]):
        merged, result = acc
        merged_lo, merged_hi = merged
        lo, hi = el

        if (
            (merged_hi >= lo and merged_hi <= hi)
            or (merged_lo >= lo and merged_lo <= hi)
            or (merged_lo <= lo and merged_hi >= hi)
        ):
            return (min(merged_lo, lo), max(merged_hi, hi)), result
        elif merged_hi < lo:
            result.append(merged)
            return el, result
        else:
            result.append(el)
            return merged, result

    def __init__(self, gen_params: GenParams, value=0) -> None:
        super().__init__()

        # poor man's interval list
        self.segments = []

        self.value_out = value  # attr value if memory addr out of any segment
        self.value_in = 1 - value  # attr value if memory within segment

        self.in_addr = Signal(gen_params.isa.xlen)
        self.out = Signal(1)

    def add_range(self, range: tuple[int, int]):
        low, high = range
        last, rest = reduce(PhysMemAttr.merge_intervals, self.segments, ((low, high), []))
        rest.append(last)
        self.segments = rest

    def elaborate(self, platform) -> HasElaborate:
        m = Module()

        if len(self.segments) == 0:
            # There is no memory segment for which the attribute is true.
            m.d.comb += self.out.eq(self.value_out)
        else:
            # Build if-else expression that checks if `in_addr` is in segment range.
            for i in range(len(self.segments)):
                low, high = self.segments[i]
                if i == 0:
                    with m.If(self.in_addr >= low and self.in_addr <= high):
                        m.d.comb += self.out.eq(self.value_in)
                else:
                    with m.Elif(self.in_addr >= low and self.in_addr <= high):
                        m.d.comb += self.out.eq(self.value_in)

            with m.Else():
                m.d.comb += self.out.eq(self.value_out)

        return m


class PMAChecker(Elaboratable):

    """
    Implementation of physical memory attributes checker. It may or may not be a part of LSU.
    `PMAChecker` exposes method `ask` that can be used to request information about given memory
    address. Result of `ask` method contains bit vector of all defined PMAs.

    Attributes
    ----------
    ask : Method
        Used to request attributes of particular memory address.
    """

    ATTR_WIDTH = 1

    def __init__(self, gen_params: GenParams) -> None:
        super().__init__()

        self.attr_width = PMAChecker.ATTR_WIDTH
        self.ask = Method(i=[("in_addr", gen_params.isa.xlen)], o=gen_params.get(PMALayouts).pma_attrs_layout)
        self.attrs = dict()
        self.attrs["mmio"] = PhysMemAttr(gen_params)

        if gen_params.mmio is not None:
            for mmio_range in gen_params.mmio:
                self.attrs["mmio"].add_range(mmio_range)

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        for attr_name in self.attrs:
            m.submodules[attr_name] = self.attrs[attr_name]

        @def_method(m, self.ask)
        def _(in_addr: Value):
            out_signals = dict()
            for attr_name in self.attrs:
                attr = self.attrs[attr_name]
                out = Signal(1)
                m.d.comb += attr.in_addr.eq(in_addr)
                m.d.comb += out.eq(attr.out)
                out_signals[attr_name] = out

            return out_signals

        return m
