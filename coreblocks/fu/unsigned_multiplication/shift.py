from amaranth import *

from coreblocks.fu.unsigned_multiplication.common import MulBaseUnsigned
from coreblocks.params import GenParams
from coreblocks.transactions.core import def_method

__all__ = ["ShiftUnsignedMul"]


class ShiftUnsignedMul(MulBaseUnsigned):
    """
    Module with @see{MulBaseUnsigned} interface performing cheap multi clock cycle multiplication using
    Russian Peasants Algorithm.
    """

    def __init__(self, gen: GenParams):
        super().__init__(gen)

    def elaborate(self, platform):
        m = Module()
        res = Signal(unsigned(self.gen.isa.xlen * 2))

        i1 = Signal(unsigned(self.gen.isa.xlen * 2))
        i2 = Signal(unsigned(self.gen.isa.xlen))
        accepted = Signal(1, reset=1)

        @def_method(m, self.issue, ready=accepted)
        def _(arg):
            m.d.sync += res.eq(0)
            m.d.sync += i1.eq(arg.i1)
            m.d.sync += i2.eq(arg.i2)
            m.d.sync += accepted.eq(0)

        @def_method(m, self.accept, ready=(~i2.bool() & ~accepted))
        def _(arg):
            m.d.sync += accepted.eq(1)
            return {"o": res}

        with m.If(~accepted):
            with m.If(i2[0]):
                m.d.sync += res.eq(res + i1)
            m.d.sync += i1.eq(i1 << 1)
            m.d.sync += i2.eq(i2 >> 1)

        return m
