from abc import abstractmethod
from amaranth import *

from coreblocks.params import GenParams
from coreblocks.interface.layouts import UnsignedMulUnitLayouts
from transactron import *
from transactron.core import def_method

__all__ = ["MulBaseUnsigned", "DSPMulUnit"]


class MulBaseUnsigned(Elaboratable):
    """
    Abstract module creating common interface of unsigned multiplication module.

    Attributes
    ----------
    issue: Method(i=gen.get(UnsignedMulUnitLayouts).issue), in
        Method used for requesting computation.
    accept: Method(i=gen.get(UnsignedMulUnitLayouts).accept), out
        Method used for getting result of requested computation.
    """

    def __init__(self, gen_params: GenParams, dsp_width: int = 32):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        self.dsp_width = dsp_width

        layout = gen_params.get(UnsignedMulUnitLayouts)

        self.issue = Method(i=layout.issue)
        self.accept = Method(o=layout.accept)

    @abstractmethod
    def elaborate(self, platform) -> TModule:
        raise NotImplementedError()


class DSPMulUnit(Elaboratable):
    """
    Module for 1 clock cycle multiplication, designed to be replaced with a DSP block by the synthesis tool.

    Attributes
    ----------
    compute: Method(i=[("i1", n), ("i2", n)], o=[("o", 2 * n)]), in out
        Method for requesting computations and getting results in this same cycle.
    """

    def __init__(self, dsp_width: int):
        """
        Parameters
        ----------
        dsp_width: int
            Bit width of multiplied numbers.
        """
        self.n = n = dsp_width

        self.compute = Method(i=[("i1", n), ("i2", n)], o=[("o", 2 * n)])

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.compute)
        def _(arg):
            # Here will be connection to DSP but right now I have no idea how to do it
            return {"o": arg.i1 * arg.i2}

        return m
