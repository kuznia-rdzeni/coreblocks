from amaranth import *

from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
from coreblocks.params import GenParams
from transactron import *
from transactron.core import def_method

__all__ = ["IterativeSequentialUnsignedMul"]


class IterativeWithSingleDSPMul(Elaboratable):
    def __init__(self, dsp: DSPMulUnit, n: int):
        self.n = n
        self.dsp = dsp

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))
        self.confirm = Signal(reset=0)
        self.reset = Signal()

    def elaborate(self, platform) -> TModule:
        if self.n <= self.dsp.n:
            m = TModule()
            with m.If(self.reset):
                m.d.sync += self.confirm.eq(0)

            with m.If(~self.confirm & ~self.reset):
                with Transaction().body(m):
                    res = self.dsp.compute(m, i1=self.i1, i2=self.i2)
                    m.d.sync += self.result.eq(res)
                    m.d.sync += self.confirm.eq(1)

            return m
        else:
            m = TModule()
            # TODO
            m.d.sync += self.result.eq(1)
            m.d.sync += self.confirm.eq(1)
            return m


class IterativeSequentialUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing sequential multiplication using single DSP unit.
    It uses classic recursive multiplication algorithm.
    """

    def __init__(self, gen_params: GenParams, dsp_width: int = 8):
        super().__init__(gen_params)
        self.dsp_width = dsp_width

    def elaborate(self, platform):
        m = TModule()
        m.submodules.dsp = dsp = DSPMulUnit(self.dsp_width)
        m.submodules.multiplier = multiplier = IterativeWithSingleDSPMul(dsp, self.gen_params.isa.xlen)

        accepted = Signal(1, reset=1)
        m.d.sync += multiplier.reset.eq(0)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += multiplier.i1.eq(arg.i1)
            m.d.sync += multiplier.i2.eq(arg.i2)

            m.d.sync += multiplier.reset.eq(1)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~accepted) & multiplier.confirm & ~multiplier.reset)
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": multiplier.result}

        return m
