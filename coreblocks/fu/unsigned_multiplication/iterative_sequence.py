from amaranth import *
import math
# from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
# from coreblocks.params import GenParams
# from transactron import *
# from transactron.core import def_method

__all__ = ["IterativeSequenceMul"]


class IterativeSequenceMul(Elaboratable):
    def __init__(self, dsp_width: int, n: int):
        self.n = n
        self.dsp_width = dsp_width

        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))

        self.pipline_array = [[[Signal(unsigned(n*2)) for _ in range(n)] for _ in range(n)] for _ in range(n)]

    def elaborate(self):
        m = Module()

        number_of_chunks = self.n // self.dsp_width

        for j in range(number_of_chunks):
            chunk_i1 = self.i1[j*self.dsp_width : (j+1)*self.dsp_width]
            for i in range(number_of_chunks):
                chunk_i2 = self.i2[i*self.dsp_width:(i+1)*self.dsp_width]
                m.d.sync += self.pipline_array[0][j][i].eq(chunk_i1*chunk_i2)

        for i in range(1, n):
            for j in range(n-1):
                for k in range(n-1):
                    ll = pipline_array[i-1][j][k]
                    lu = pipline_array[i-1][j][k+1]
                    ul = pipline_array[i-1][j+1][k]
                    uu = pipline_array[i-1][j+1][k+1]
                    m.d.sync += self.pipline_array[i][j][k].eq(ll+((ul+lu) << self.n // 2) + (uu << self.n))
        result_lvl = math.log(self.n - self.dps_width, 2)
        m.d.sync += self.result.eq(self.pipline_array[result_lvl][0][0])
        return m
