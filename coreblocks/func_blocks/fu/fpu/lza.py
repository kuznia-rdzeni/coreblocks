from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams


class LZAMethodLayout:
    """LZA module layouts for methods
    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
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
        def _(arg):
            t = Signal(self.lza_params.sig_width + 1)
            g = Signal(self.lza_params.sig_width + 1)
            z = Signal(self.lza_params.sig_width + 1)
            f = Signal(self.lza_params.sig_width)
            shift_amount = Signal(range(self.lza_params.sig_width))
            is_zero = Signal(1)

            m.d.av_comb += t.eq((arg.sig_a ^ arg.sig_b) << 1)
            m.d.av_comb += g.eq((arg.sig_a & arg.sig_b) << 1)
            m.d.av_comb += z.eq(((~(arg.sig_a) & ~(arg.sig_b)) << 1))
            with m.If(arg.carry):
                m.d.av_comb += g[0].eq(1)
            with m.Else():
                m.d.av_comb += z[0].eq(1)

            for i in reversed(range(1, self.lza_params.sig_width + 1)):
                m.d.av_comb += f[i - 1].eq((t[i] ^ ~(z[i - 1])))

            m.d.av_comb += shift_amount.eq(0)
            for i in reversed(range(self.lza_params.sig_width)):
                with m.If(f[self.lza_params.sig_width - i - 1]):
                    m.d.av_comb += shift_amount.eq(i)

            m.d.av_comb += is_zero.eq((arg.carry & t[1 : self.lza_params.sig_width].all()))

            return {
                "shift_amount": shift_amount,
                "is_zero": is_zero,
            }

        return m
