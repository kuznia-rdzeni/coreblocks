from dataclasses import dataclass
from functools import reduce
from operator import or_
from amaranth import *
from amaranth.lib import data

from coreblocks.params import *
from transactron.utils import HasElaborate
from transactron.core import TModule


@dataclass
class PMARegion:
    """
    Data class for physical memory attributes contiguous region of memory. Region of memory
    includes both start and end address.

    Attributes
    ----------
    start : int
        Defines beginning of region, start address is included in the region.
    end : int
        Defines end of region, end address is included in the region.
    mmio : bool
        Value True for this field indicates that memory region is MMIO.
    """

    start: int
    end: int
    mmio: bool = False


class PMALayout(data.StructLayout):
    def __init__(self):
        super().__init__({"mmio": unsigned(1)})


class PMAChecker(Elaboratable):
    """
    Implementation of physical memory attributes checker. It may or may not be a part of LSU.
    This is a combinational circuit with return value read from `result` output.

    Attributes
    ----------
    addr : Signal
        Memory address, for which PMAs are requested.
    result : View
        PMAs for given address.
    """

    def __init__(self, gen_params: GenParams) -> None:
        # poor man's interval list
        self.segments = gen_params.pma
        self.result = Signal(PMALayout())
        self.addr = Signal(gen_params.isa.xlen)

    def elaborate(self, platform) -> HasElaborate:
        m = TModule()

        outputs = [Signal(PMALayout()) for _ in self.segments]

        # zero output if addr not in region, propagate value if addr in region
        for i, segment in enumerate(self.segments):
            start = segment.start
            end = segment.end

            # check if addr in region
            with m.If((self.addr >= start) & (self.addr <= end)):
                m.d.comb += outputs[i].eq(segment.mmio)

        # OR all outputs
        m.d.comb += self.result.eq(reduce(or_, [Value.cast(o) for o in outputs], 0))

        return m
