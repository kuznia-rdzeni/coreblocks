from amaranth import *
from amaranth.utils import ceil_log2
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from transactron.utils.amaranth_ext import count_leading_zeros


class LZAMethodLayout:
    """LZA module layouts for methods

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        """
        sig_a - significand of a
        sig_b - significand of b
        carry - indicates if we want to predict result of a+b or a+b+1
        shift_amount - position to shift needed to normalize number
        is_zero - indicates if result is zero
        """
        self.predict_in_layout = [
            ("sig_a", fpu_params.sig_width),
            ("sig_b", fpu_params.sig_width),
            ("carry", 1),
        ]
        self.predict_out_layout = [
            ("shift_amount", range(fpu_params.sig_width)),
            ("is_zero", 1),
        ]


class LZAModule(Elaboratable):
    """LZA module
    Based on: https://userpages.cs.umbc.edu/phatak/645/supl/lza/lza-survey-arith01.pdf
    After performing subtracion, we may have to normalize floating point numbers and
    For that, we have to know the number of leading zeros.
    The most basic approach includes using LZC (leading zero counter) after subtracion,
    a more advanced approach includes using LZA (Leading Zero Anticipator) to predict the number of
    leading zeroes. It is worth noting that this LZA module works under assumptions that
    significands are in two's complement and that before complementation sig_a was greater
    or equal to sig_b. Another thing worth noting is that LZA works with error = 1.
    That means that if 'n' is the result of the LZA module, in reality, to normalize
    number we may have to shift left by 'n' or 'n+1'. There are few techniques of
    dealing with that error like specially designed shifters or predicting the error
    but the most basic approach is to just use multiplexer after shifter to perform
    one more shift left if necessary.

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    predict_request: Method
        Transactional method for initiating leading zeros prediction.
        Takes 'predict_in_layout' as argument
        Returns shift amount as 'predict_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.lza_params = fpu_params
        self.method_layouts = LZAMethodLayout(fpu_params=self.lza_params)
        self.predict_request = Method(
            i=self.method_layouts.predict_in_layout,
            o=self.method_layouts.predict_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.predict_request)
        def _(sig_a, sig_b, carry):
            f_size = 2 ** ceil_log2(self.lza_params.sig_width)
            filler_size = f_size - self.lza_params.sig_width
            lower_ones = Const((2**filler_size) - 1, f_size)

            t = Signal(self.lza_params.sig_width + 1)
            g = Signal(self.lza_params.sig_width + 1)
            z = Signal(self.lza_params.sig_width + 1)
            f = Signal(f_size)
            shift_amount = Signal(range(self.lza_params.sig_width))
            is_zero = Signal(1)

            m.d.av_comb += t.eq((sig_a ^ sig_b) << 1)
            m.d.av_comb += g.eq((sig_a & sig_b) << 1)
            m.d.av_comb += z.eq(((sig_a | sig_b) << 1))
            with m.If(carry):
                m.d.av_comb += g[0].eq(1)
                m.d.av_comb += z[0].eq(1)

            for i in reversed(range(1, self.lza_params.sig_width + 1)):
                m.d.av_comb += f[i + filler_size - 1].eq((t[i] ^ z[i - 1]))

            m.d.av_comb += shift_amount.eq(0)
            m.d.av_comp += f.eq(f | lower_ones)
            m.d.av_comb += shift_amount.eq(count_leading_zeros(f))

            m.d.av_comb += is_zero.eq((carry & t[1 : self.lza_params.sig_width].all()))

            return {
                "shift_amount": shift_amount,
                "is_zero": is_zero,
            }

        return m
