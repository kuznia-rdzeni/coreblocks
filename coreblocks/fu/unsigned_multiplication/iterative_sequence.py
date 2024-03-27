from amaranth import *
import math

from amaranth.sim import Simulator, Delay
# from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
# from coreblocks.params import GenParams
# from transactron import *
# from transactron.core import def_method
import random  
__all__ = ["IterativeSequenceMul"]


class IterativeSequenceMul(Elaboratable):
    def __init__(self, dsp_width: int, dsp_number: int, n: int):
        self.n = n
        self.dsp_width = dsp_width
        self.dsp_number = dsp_number
	
        self.multiplication_step =  Signal(unsigned(n))
        self.first_mul_number =  Signal(unsigned(n))
        self.last_mul_number = Signal(unsigned(n))
        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))

        self.pipeline_array = [[[Signal(unsigned(n*2)) for _ in range(n)] for _ in range(n)] for _ in range(n)]

    def elaborate(self, platform=None):
        m = Module()

        number_of_chunks = self.n // self.dsp_width
        number_of_multiplications = number_of_chunks * number_of_chunks
        number_of_steps = math.ceil(number_of_multiplications / self.dsp_number)
	
        m.d.sync += self.multiplication_step.eq((self.multiplication_step + 1) % number_of_steps)
        m.d.comb += self.first_mul_number.eq( self.multiplication_step * self.dsp_number)
        m.d.comb += self.last_mul_number.eq((self.multiplication_step + 1) * self.dsp_number)

        
        for i in range(number_of_multiplications):
            a = (i // number_of_chunks)
            b = (i % number_of_chunks)
            chunk_i1 = self.i1[a*self.dsp_width: (a+1)*self.dsp_width]
            chunk_i2 = self.i2[b*self.dsp_width: (b+1)*self.dsp_width]
            with m.If((i >= self.first_mul_number) & (i < self.last_mul_number)):  
                m.d.sync += self.pipeline_array[0][a][b].eq(chunk_i1*chunk_i2)
	
        shift_size = self.dsp_width
        for i in range(1, int(math.log(number_of_chunks, 2))+1):
            shift_size = shift_size << 1
            for j in range(number_of_chunks >> i):
                for k in range(number_of_chunks >> i):
                    ll = self.pipeline_array[i-1][2*j][2*k]
                    lu = self.pipeline_array[i-1][2*j][2*k+1]
                    ul = self.pipeline_array[i-1][2*j+1][2*k]
                    uu = self.pipeline_array[i-1][2*j+1][2*k+1]
                    m.d.sync += self.pipeline_array[i][j][k].eq(ll+((ul+lu) << (shift_size >> 1)) + (uu << shift_size) )
        result_lvl = int(math.log(number_of_chunks, 2)) 
        m.d.sync += self.result.eq(self.pipeline_array[result_lvl][0][0])
        return m
        
# Random pipelining test of the module - works
def testbench(t):
    dsp_width = 4
    n = 16
    mul_module = IterativeSequenceMul(dsp_width=dsp_width, dsp_number=4, n=n)
    sim = Simulator(mul_module)
    sim.add_clock(1e-6)

    def process():

        initial_test_cases = [(random.randint(1, 0xFFFF), random.randint(1, 0xFFFF)) for _ in range(t)]
        test_cases = [(a, b) for a, b in initial_test_cases for _ in range(4)]
        expected_results = [(a * b) for a, b in initial_test_cases for _ in range(4)]

        module_latency = int(math.log2(n / dsp_width)) + 3 + 3
	
        for test_idx, (test_val1, test_val2) in enumerate(test_cases + [(0, 0)] * module_latency):
           
            yield mul_module.i1.eq(test_val1)
            yield mul_module.i2.eq(test_val2)
            #if test_val1 != 0:
            # 	print(f"i1 --> {test_val1} i2 --> {test_val2}") 
            #print("Next cycle")
            #multiplication_step_val = yield mul_module.multiplication_step
            #first_mul_number_val = yield mul_module.first_mul_number
            #last_mul_number_val = yield mul_module.last_mul_number
            #print(f"multiplication_step: {multiplication_step_val}, first_mul_number: {first_mul_number_val}, last_mul_number: {last_mul_number_val}")
            #for i in range(n):
            #    for j in range(n):
            #        for k in range(n):
            #            # Access and print the value of each signal in the pipeline_array
            #            val = yield mul_module.pipeline_array[i][j][k]
            #            if val !=0:
            #                print(f"pipeline_array[{i}][{j}][{k}] = {val}")
                        
            if test_idx >= module_latency and (test_idx - module_latency) % 4 == 0:
                expected = expected_results[test_idx - module_latency]
                result = yield mul_module.result
                assert result == expected, f"Test case {(test_idx - module_latency)//4} failed: Expected {expected}, got {result}"
                print(f"Test case {(test_idx - module_latency)//4}: Expected = {expected}, got {result}")
            yield

    sim.add_sync_process(process)
    sim.run()

if __name__ == "__main__":
    t = 100
    testbench(t)


