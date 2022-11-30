from amaranth import *

from coreblocks.params import GenParams, UnsignedMulUnitLayouts
from coreblocks.transactions import *
from coreblocks.transactions.core import def_method

__all__ = ["MulBaseUnsigned", "DSPMulUnit"]


class MulBaseUnsigned(Elaboratable):
    """
    Abstract module creating common interface of unsigned multiplication module.
    """

    def __init__(self, gen: GenParams):
        self.gen = gen

        layout = gen.get(UnsignedMulUnitLayouts)

        self.issue = Method(i=layout.issue)
        self.accept = Method(o=layout.accept)


class DSPMulUnit(Elaboratable):
    """
    Module for 1 clock cycle multiplication, designed to be replaced with a DSP block by the synthesis tool.

    Parameters
    ----------
    dsp_width: int
        Bit width of multiplied numbers.
    """

    def __init__(self, dsp_width: int):
        self.n = n = dsp_width

        self.compute = Method(i=[("i1", n), ("i2", n)], o=[("o", 2 * n)])

    def elaborate(self, platform):
        m = Module()

        @def_method(m, self.compute)
        def _(arg):
            # Here will be connection to DSP but right now I have no idea how to do it
            return {"o": arg.i1 * arg.i2}

        return m
