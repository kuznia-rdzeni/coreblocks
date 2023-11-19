from dataclasses import dataclass
from amaranth import *

from coreblocks.params import *
from transactron.utils import HasElaborate
from transactron.core import TModule


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
    mmio: bool


class PMAChecker(Elaboratable):

    """
    Implementation of physical memory attributes checker. It may or may not be a part of LSU.
    `PMAChecker` exposes method `ask` that can be used to request information about given memory
    address. Result of `ask` method contains bit vector of all defined PMAs.

    Attributes
    ----------

    addr : Signal
        Memory address, for which PMAs are requested.

    result : Record
        PMAs for given address.

    """

    def __init__(self, gen_params: GenParams) -> None:
        super().__init__()

        # poor man's interval list
        self.segments = gen_params.pma
        self.attr_layout = gen_params.get(PMALayouts).pma_attrs_layout
        self.result = Record(self.attr_layout)
        self.addr = Signal(gen_params.isa.xlen)

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        outputs = Array([Record(self.attr_layout) for _ in self.segments])

        # zero output if addr not in region, propagate value if addr in region
        for i, segment in enumerate(self.segments):
            start = segment.start
            end = segment.end

            # check if addr in region
            with m.If((self.addr >= start).bool() & (self.addr <= end).bool()):
                m.d.comb += outputs[i].eq(segment.mmio)
            with m.Else():
                m.d.comb += outputs[i].eq(0x0)

        # OR all outputs
        for output in outputs:
            m.d.comb += self.result.eq(self.result | output)

        return m
