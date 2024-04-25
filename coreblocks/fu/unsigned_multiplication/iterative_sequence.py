from amaranth import *
import math

from amaranth.sim import Simulator, Delay
from coreblocks.fu.unsigned_multiplication.common import DSPMulUnit, MulBaseUnsigned
from coreblocks.params import GenParams
from transactron import *
from transactron.core import def_method
import random  
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit
from coreblocks.params.configurations import test_core_config
from transactron.lib import FIFO

__all__ = ["IterativeSequenceMul"]


class IterativeSequenceMul(Elaboratable):
    def __init__(self, dsp_width: int, dsp_number: int, n: int):
        self.n = n
        self.dsp_width = dsp_width
        self.dsp_number = dsp_number
	
        self.ready = Signal(unsigned(1))
        self.issue = Signal(unsigned(1))
        self.step =  Signal(unsigned(n))
        self.first_mul_number =  Signal(unsigned(n))
        self.last_mul_number = Signal(unsigned(n))
        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))
        self.valid = Signal(unsigned(1))
        self.getting_result = Signal(unsigned(1))

        self.pipeline_array = [[[Signal(unsigned(n*2)) for _ in range(n)] for _ in range(n)] for _ in range(n)]
        self.valid_array = [Signal(unsigned(1)) for _ in range(n)]
    def elaborate(self, platform=None):
        m = Module()
        
        
        number_of_chunks = self.n // self.dsp_width
        number_of_multiplications = number_of_chunks * number_of_chunks
        number_of_steps = math.ceil(number_of_multiplications / self.dsp_number)
        result_lvl = int(math.log(number_of_chunks, 2))

        with m.If(~self.valid | self.getting_result):
            m.d.sync += self.step.eq((self.step + 1) % number_of_steps)
            
            for i in range(1,result_lvl+1):
                m.d.sync += self.valid_array[i].eq(self.valid_array[i-1])

            with m.If(self.step == number_of_steps):
                m.d.sync += self.ready.eq(1)

            with m.If(self.step == number_of_steps - 1):
                m.d.sync += self.valid_array[0].eq(1)
            with m.Else():
                m.d.sync += self.valid_array[0].eq(0)

                
            with m.If(self.step < number_of_steps):
                m.d.sync += self.ready.eq(0)
                m.d.sync += self.step.eq(self.step+1)
                
            with m.If(self.issue == 1):
                m.d.sync += self.step.eq(0)
                m.d.sync += self.ready.eq(0)
            
                
            m.d.sync += self.first_mul_number.eq(( self.first_mul_number + self.dsp_number) % number_of_multiplications)

            
            for i in range(number_of_multiplications):
                a = (i // number_of_chunks)
                b = (i % number_of_chunks)
                chunk_i1 = self.i1[a*self.dsp_width: (a+1)*self.dsp_width]
                chunk_i2 = self.i2[b*self.dsp_width: (b+1)*self.dsp_width]
                with m.If((i >= self.first_mul_number) & (i <  self.first_mul_number + self.dsp_number )):
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
             
            m.d.sync += self.result.eq(self.pipeline_array[result_lvl][0][0])
            m.d.sync += self.valid.eq(self.valid_array[result_lvl])

        with m.Else():
            for i in range(self.n):
                for j in range(self.n):
                    for k in range(self.n):
                        m.d.sync += self.pipeline_array[i][j][k].eq(self.pipeline_array[i][j][k])
            m.d.sync += self.result.eq(self.result)
            m.d.sync += self.valid.eq(self.valid)
            for i in range(self.n):
                m.d.sync += self.valid_array[i].eq(self.valid_array[i])
            m.d.sync += self.step.eq(self.step)
            m.d.sync += self.ready.eq(self.ready)
            m.d.sync += self.first_mul_number.eq(self.first_mul_number)
            m.d.sync += self.last_mul_number.eq(self.last_mul_number)
        return m
        
class IterativeUnsignedMul(MulBaseUnsigned):
    

    def __init__(self, gen_params: GenParams, dsp_width: int = 4, dsp_number: int =4 ):
        super().__init__(gen_params)
        self.dsp_width = dsp_width
        self.dsp_number = dsp_number
        self.last_ready = Signal(unsigned(1))
        self.waits = [Signal(10) for _ in range(10)]
        self.waits_iter = Signal(unsigned(0))

    def elaborate(self, platform):
        m = TModule()
        m.submodules.fifo = fifo = FIFO([("o", 2 * self.gen_params.isa.xlen)], 2)

        m.submodules.mul = mul = IterativeSequenceMul(self.dsp_width, self.dsp_number, self.gen_params.isa.xlen)
        m.d.sync +=  self.last_ready.eq(mul.ready)
        
        for i in range(10):
            with m.If(self.waits[i] == 1):
                with Transaction().body(m):
                    fifo.write(m, o=mul.result)


            with m.If(self.waits[i] > 0):
                m.d.sync+= self.waits[i].eq(self.waits[i]-1)


        @def_method(m, self.issue, ready = mul.ready)
        def _(arg):
            m.d.comb += self.method_working.eq(1)
            m.d.sync += mul.i1.eq(arg.i1)
            m.d.sync += mul.i2.eq(arg.i2)
            m.d.sync += mul.issue.eq(1)
            m.d.sync += self.waits[self.waits_iter].eq(8)
            with m.If(self.waits_iter < 9):
                self.waits_iter.eq(self.waits_iter+1)

            with m.If(self.waits_iter == 9):
                self.waits_iter.eq(0)



        @def_method(m, self.accept)
        def _(arg):
            return fifo.read(m)

        return m
# Random pipelining test of the module - works
def testbench(t):
    dsp_width = 4
    n = 16
    mul_module = IterativeSequenceMul(dsp_width=dsp_width, dsp_number=4, n=n)
    sim = Simulator(mul_module)
    sim.add_clock(1e-6)

    def process():

        test_cases = [(random.randint(1, 0xFFFF), random.randint(1, 0xFFFF)) for _ in range(t)]
        test_cases = [(65535,65535),(500,100),(8902,123),(2131,323)]
        expected_results = [(a * b) for a, b in test_cases]
        time = 0
        module_latency = 1
        test_it=0
        for time in range(30):         
            ready_signal = yield mul_module.ready
            if ready_signal == 1:
                test_val1,test_val2 = test_cases[test_it]
                test_it = test_it + 1
                print(f"giving values: {test_val1}, {test_val2} = {test_val1 * test_val2}")
                yield mul_module.i1.eq(test_val1)
                yield mul_module.i2.eq(test_val2)
                yield mul_module.issue.eq(1)
            else:
                yield mul_module.issue.eq(0)
            

            result_sig = yield mul_module.result
            valid_sig = yield mul_module.valid
            ready_signal = yield mul_module.ready
            if valid_sig == 1 and random.randint(0, 1) == 1:
                yield mul_module.getting_result.eq(1)
            else:
                yield mul_module.getting_result.eq(0)
            print(f" time: {time} result: {result_sig} valid_sig: {valid_sig} ready_sig: {ready_signal}")
            yield
            """
            for i in range(n):
                for j in range(n):
                    for k in range(n):
                        # Access and print the value of each signal in the pipeline_array
                        val = yield mul_module.pipeline_array[i][j][k]
                        if val !=0:
                            print(f"pipeline_array[{i}][{j}][{k}] = {val}")
            """
            """
            while True:
                valid_signal = yield mul_module.valid
                if valid_signal == 1:

            if test_idx >= module_latency:
                expected = expected_results[test_idx - module_latency]
                result = yield mul_module.result
                assert result == expected, f"Test case {(test_idx - module_latency)} failed: Expected {expected}, got {result}"
                print(f"Test case {(test_idx - module_latency)}: Expected = {expected}, got {result}")
            """
            

    sim.add_sync_process(process)
    sim.run()

def transactron_testbench():
    gen_params = GenParams(test_core_config)
    mul_module = IterativeUnsignedMul(gen_params)
    tmul_module = SimpleTestCircuit(mul_module)
    sim = Simulator(tmul_module)
    sim.add_clock(1e-6)
    def transactron_process():
        res = yield from tmul_module.issue.call({"i1":5, "i2": 7})
        for _ in range(40):
            yield
        print(res)
    sim.add_sync_process(transactron_process)
    sim.run()
if __name__ == "__main__":
    t = 100
    testbench(t)
    #transactron_testbench()


