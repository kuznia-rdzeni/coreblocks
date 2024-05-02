from amaranth import *
import math


from coreblocks.func_blocks.fu.unsigned_multiplication.common import MulBaseUnsigned
from coreblocks.params import GenParams
from transactron import *
from transactron.core import def_method


__all__ = ["IterativeUnsignedMul"]


class IterativeSequenceMul(Elaboratable):
    def __init__(self, dsp_width: int, dsp_number: int, n: int):
        self.n = n
        self.dsp_width = dsp_width
        self.dsp_number = dsp_number

        self.ready = Signal(unsigned(1))
        self.issue = Signal(unsigned(1))
        self.step = Signal(unsigned(n), reset=math.ceil((self.n // self.dsp_width) ** 2 / self.dsp_number))
        self.first_mul_number = Signal(unsigned(n))
        self.last_mul_number = Signal(unsigned(n))
        self.i1 = Signal(unsigned(n))
        self.i2 = Signal(unsigned(n))
        self.result = Signal(unsigned(n * 2))
        self.valid = Signal(unsigned(1))
        self.getting_result = Signal(unsigned(1))

        self.pipeline_array = [[[Signal(unsigned(n * 2)) for _ in range(n)] for _ in range(n)] for _ in range(n)]
        self.valid_array = [Signal(unsigned(1)) for _ in range(n)]

    def elaborate(self, platform=None):
        m = TModule()

        number_of_chunks = self.n // self.dsp_width
        number_of_multiplications = number_of_chunks**2
        number_of_steps = math.ceil(number_of_multiplications / self.dsp_number)
        result_lvl = int(math.log(number_of_chunks, 2))

        with m.If(~self.valid | self.getting_result):
            for i in range(1, result_lvl + 1):
                m.d.sync += self.valid_array[i].eq(self.valid_array[i - 1])

            with m.If(self.step == number_of_steps):
                m.d.sync += self.ready.eq(1)

            with m.If(self.step == number_of_steps - 1):
                m.d.sync += self.valid_array[0].eq(1)
            with m.Else():
                m.d.sync += self.valid_array[0].eq(0)

            with m.If(self.step < number_of_steps):
                m.d.sync += self.ready.eq(0)
                m.d.sync += self.step.eq(self.step + 1)

            with m.If(self.issue):
                m.d.sync += self.step.eq(0)
                m.d.sync += self.ready.eq(0)

            m.d.sync += self.first_mul_number.eq((self.first_mul_number + self.dsp_number) % number_of_multiplications)

            for i in range(number_of_multiplications):
                a = i // number_of_chunks
                b = i % number_of_chunks
                chunk_i1 = self.i1[a * self.dsp_width : (a + 1) * self.dsp_width]
                chunk_i2 = self.i2[b * self.dsp_width : (b + 1) * self.dsp_width]
                with m.If((i >= self.first_mul_number) & (i < self.first_mul_number + self.dsp_number)):
                    m.d.sync += self.pipeline_array[0][a][b].eq(chunk_i1 * chunk_i2)

            shift_size = self.dsp_width
            for i in range(1, int(math.log(number_of_chunks, 2)) + 1):
                shift_size = shift_size << 1
                for j in range(number_of_chunks >> i):
                    for k in range(number_of_chunks >> i):
                        ll = self.pipeline_array[i - 1][2 * j][2 * k]
                        lu = self.pipeline_array[i - 1][2 * j][2 * k + 1]
                        ul = self.pipeline_array[i - 1][2 * j + 1][2 * k]
                        uu = self.pipeline_array[i - 1][2 * j + 1][2 * k + 1]
                        m.d.sync += self.pipeline_array[i][j][k].eq(
                            ll + ((ul + lu) << (shift_size >> 1)) + (uu << shift_size)
                        )

            m.d.sync += self.result.eq(self.pipeline_array[result_lvl][0][0])
            m.d.sync += self.valid.eq(self.valid_array[result_lvl])

        return m


class IterativeUnsignedMul(MulBaseUnsigned):
    def __init__(self, gen_params: GenParams, dsp_width: int = 4, dsp_number: int = 4):
        super().__init__(gen_params)
        self.dsp_width = dsp_width
        self.dsp_number = dsp_number

    def elaborate(self, platform):
        m = TModule()
        m.submodules.mul = mul = IterativeSequenceMul(self.dsp_width, self.dsp_number, self.gen_params.isa.xlen)

        @def_method(m, self.issue, ready=mul.ready)
        def _(arg):
            m.d.sync += mul.i1.eq(arg.i1)
            m.d.sync += mul.i2.eq(arg.i2)
            m.d.comb += mul.issue.eq(1)

        @def_method(m, self.accept, ready=mul.valid)
        def _(arg):
            m.d.comb += mul.getting_result.eq(1)
            return mul.result

        return m
