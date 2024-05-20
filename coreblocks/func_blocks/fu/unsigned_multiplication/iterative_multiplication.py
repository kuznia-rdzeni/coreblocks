from amaranth import *
import math

from coreblocks.func_blocks.fu.unsigned_multiplication.common import MulBaseUnsigned, DSPMulUnit
from coreblocks.params import GenParams
from transactron import *
from transactron.core import def_method

__all__ = ["IterativeUnsignedMul"]


class IterativeSequenceMul(Elaboratable):
    """
    IterativeSequenceMul performs iterative unsigned multiplication using multiple DSP units.
    This class breaks down the multiplication of large bit-width operands into smaller chunks that
    fit into the DSP units,
    processes these chunks iteratively,
    and then combines the results using a multi-level pipeline to form the final product.

    Attributes
    ----------
        dsp_width (int): Width of each DSP unit.
        dsp_number (int): Number of DSP units available.
        n (int): Bit width of the numbers to be multiplied.

    Signals:
    --------
        ready (Signal): Indicates if the multiplier is ready to accept new inputs.
        issue (Signal): Signals the start of a new multiplication.
        i1 (Signal): First multiplicand, extended to align with the DSP width.
        i2 (Signal): Second multiplicand, extended to align with the DSP width.
        result (Signal): Final result of the multiplication.
        valid (Signal): Indicates if the result is valid.
        getting_result (Signal): Signals the process of retrieving the result.
    """

    def __init__(self, dsp_width: int, dsp_number: int, n: int):
        self.n = n
        self.n_padding = dsp_width * 2 ** (math.ceil(math.log2(n / dsp_width)))
        self.dsp_width = dsp_width
        self.dsp_number = dsp_number
        self.number_of_chunks = self.n_padding // self.dsp_width
        self.number_of_multiplications = self.number_of_chunks**2
        self.number_of_steps = math.ceil(self.number_of_multiplications / self.dsp_number)
        self.result_lvl = math.ceil(math.log2(self.number_of_chunks))

        self.ready = Signal()
        self.issue = Signal()
        self.step = Signal(range(self.number_of_steps + 1), reset=self.number_of_steps)
        self.i1 = Signal(self.n_padding)
        self.i2 = Signal(self.n_padding)
        self.result = Signal(2 * n)
        self.valid = Signal()
        self.getting_result = Signal()

        self.values_array = [
            [
                [Signal(self.dsp_width * (1 << i) * 2) for _ in range(self.number_of_chunks >> i)]
                for _ in range(self.number_of_chunks >> i)
            ]
            for i in range(self.result_lvl + 1)
        ]
        self.valid_array = [Signal() for _ in range(self.result_lvl + 1)]

    def elaborate(self, platform=None):
        m = TModule()

        self.dsp_units = []
        for i in range(self.dsp_number):
            unit = DSPMulUnit(self.dsp_width)
            self.dsp_units.append(unit)
            setattr(m.submodules, f"dsp_unit_{i}", unit)

        with m.If((self.step < (self.number_of_steps - 1)) | (self.valid & ~self.getting_result)):
            m.d.comb += self.ready.eq(0)
        with m.Else():
            m.d.comb += self.ready.eq(1)

        m.d.comb += self.result.eq(self.values_array[self.result_lvl][0][0])
        m.d.comb += self.valid.eq(self.valid_array[self.result_lvl])

        with m.If(~self.valid | self.getting_result):
            for i in range(1, self.result_lvl + 1):
                m.d.sync += self.valid_array[i].eq(self.valid_array[i - 1])

            with m.If(self.step == self.number_of_steps - 1):
                m.d.sync += self.valid_array[0].eq(1)
            with m.Else():
                m.d.sync += self.valid_array[0].eq(0)

            with m.If(self.step < self.number_of_steps):
                m.d.sync += self.step.eq(self.step + 1)

            with m.If(self.issue):
                m.d.sync += self.step.eq(0)

            dsp_idx = 0
            for i in range(self.number_of_multiplications):
                a = i // self.number_of_chunks
                b = i % self.number_of_chunks
                chunk_i1 = self.i1[a * self.dsp_width : (a + 1) * self.dsp_width]
                chunk_i2 = self.i2[b * self.dsp_width : (b + 1) * self.dsp_width]
                with m.If((i >= self.step * self.dsp_number) & (i < (self.step + 1) * self.dsp_number)):
                    dsp_idx = (dsp_idx + 1) % self.dsp_number
                    with Transaction().body(m):
                        res = self.dsp_units[dsp_idx].compute(m, i1=chunk_i1, i2=chunk_i2)
                        m.d.sync += self.values_array[0][a][b].eq(res)

            shift_size = self.dsp_width
            for i in range(1, self.result_lvl + 1):
                shift_size = shift_size << 1
                for j in range(self.number_of_chunks >> i):
                    for k in range(self.number_of_chunks >> i):
                        ll = self.values_array[i - 1][2 * j][2 * k]
                        lu = self.values_array[i - 1][2 * j][2 * k + 1]
                        ul = self.values_array[i - 1][2 * j + 1][2 * k]
                        uu = self.values_array[i - 1][2 * j + 1][2 * k + 1]
                        m.d.sync += self.values_array[i][j][k].eq(
                            ll + ((ul + lu) << (shift_size >> 1)) + (uu << shift_size)
                        )
        return m


class IterativeUnsignedMul(MulBaseUnsigned):
    def __init__(self, gen_params: GenParams, dsp_width: int = 18, dsp_number: int = 7):
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
