from amaranth import *
import math
from amaranth.sim import Simulator, Delay
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

        self.pipeline_array = [[[Signal(unsigned(n*2)) for _ in range(n)] for _ in range(n)] for _ in range(n)]

    def elaborate(self, platform=None):
        m = Module()

        number_of_chunks = self.n // self.dsp_width

        for j in range(number_of_chunks):
            chunk_i1 = self.i1[j*self.dsp_width : (j+1)*self.dsp_width]
            for i in range(number_of_chunks):
                chunk_i2 = self.i2[i*self.dsp_width:(i+1)*self.dsp_width]
                m.d.sync += self.pipeline_array[0][j][i].eq(chunk_i1*chunk_i2)

        for i in range(1, self.n):
            for j in range(self.n-1):
                for k in range(self.n-1):
                    ll = self.pipeline_array[i-1][j][k]
                    lu = self.pipeline_array[i-1][j][k+1]
                    ul = self.pipeline_array[i-1][j+1][k]
                    uu = self.pipeline_array[i-1][j+1][k+1]
                    m.d.sync += self.pipeline_array[i][j][k].eq(ll+((ul+lu) << self.n // 2) + (uu << self.n))
        result_lvl = int(math.log(self.n - self.dsp_width, 2))
        m.d.sync += self.result.eq(self.pipeline_array[result_lvl][0][0])
        return m

# Basic test works
def testbench():
    dsp_width = 4  
    n = 16  
    mul_module = IterativeSequenceMul(dsp_width=dsp_width, n=n)  
    sim = Simulator(mul_module)  
    sim.add_clock(1e-6)  
    def process():
        test_val1 = 3
        test_val2 = 4
        yield mul_module.i1.eq(test_val1)
        yield mul_module.i2.eq(test_val2)
        for _ in range(6): 
        	yield Delay(1e-6)
        result = yield mul_module.result
        assert result == test_val1 * test_val2, f"Expected {test_val1 * test_val2}, got {result}"
    sim.add_sync_process(process)  
    sim.run()  

if __name__ == "__main__":
    testbench()

