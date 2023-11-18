from dataclasses import dataclass
from amaranth import *

from coreblocks.params import *
from transactron.utils import HasElaborate
from transactron.core import Method, def_method, TModule


@dataclass
class PMARegion:
    """
    Data class for physical memory attributes contiguous region of memory. Region of memory
    includes both start end end address.

    Attributes
    ----------
    start : int
        Defines beginning of region.
    end : int
        Defines end of region.
    attrs : Record
        Attributes for given region. Record should follow adequate layout from `PMALayouts`.
    """

    start: int
    end: int
    attrs: Record


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

    def __init__(self, gen_params: GenParams) -> None:
        super().__init__()

        # poor man's interval list
        self.segments = gen_params.pma
        self.attr_layout = gen_params.get(PMALayouts).pma_attrs_layout
        self.ask = Method(i=[("addr", gen_params.isa.xlen)], o=self.attr_layout)

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        @def_method(m, self.ask)
        def _(addr: Value):
            result = Record(self.attr_layout)
            outputs = Array([Record(self.attr_layout) for _ in self.segments])

            # zero output if addr not in region, propagate value if addr in region
            for i, segment in enumerate(self.segments):
                start = segment.start
                end = segment.end

                # check if addr in region
                with m.If((addr >= start).bool() & (addr <= end).bool()):
                    m.d.comb += outputs[i].eq(segment.attrs)
                with m.Else():
                    m.d.comb += outputs[i].eq(0x0)

            # OR all outputs
            for output in outputs:
                m.d.comb += result.eq(result | output)

            return result

        return m
