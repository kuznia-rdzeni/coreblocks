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
            ("is_zero",1),
            ("G",fpu_params.sig_width + 2),
            ("T",fpu_params.sig_width + 2),
            ("Z",fpu_params.sig_width + 2),
            ("f",fpu_params.sig_width + 1),
            ("L",fpu_params.sig_width + 1),
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
            T = Signal(self.lza_params.sig_width + 2)
            G = Signal(self.lza_params.sig_width + 2)
            Z = Signal(self.lza_params.sig_width + 2)
            f = Signal(self.lza_params.sig_width + 1)
            L = Signal(self.lza_params.sig_width + 1)
            shift_amount = Signal(range(self.lza_params.sig_width))
            is_zero = Signal(1)

            m.d.av_comb += T.eq((arg.sig_a ^ arg.sig_b) << 1)
            m.d.av_comb += G.eq((arg.sig_a & arg.sig_b) << 1)
            m.d.av_comb += Z.eq(((~(arg.sig_a) & ~(arg.sig_b)) << 1))
            m.d.av_comb += T[-1].eq(1)
            with m.If(arg.carry):
                m.d.av_comb += G[0].eq(arg.carry)
            with m.Else():
                m.d.av_comb += Z[0].eq(1)

            for i in reversed(range(1,self.lza_params.sig_width + 2)):
                m.d.av_comb += f[i-1].eq((T[i] ^ ~(Z[i-1])))

            for i in range(self.lza_params.sig_width + 1):
                if (i == (self.lza_params.sig_width)):
                    m.d.av_comb += L[i].eq(f[i])
                else:
                    m.d.av_comb += L[i].eq(((~(f[(i+1):self.lza_params.sig_width+1]).any()) & f[i]))

            m.d.av_comb +=  shift_amount.eq(0)
            for i in range(self.lza_params.sig_width):
                with m.If(L[self.lza_params.sig_width-i-1]):
                    m.d.av_comb += shift_amount.eq(i)

            m.d.av_comb += is_zero.eq((arg.carry & T[1:self.lza_params.sig_width+1].all()))

            return {
                "shift_amount" : shift_amount,
                "is_zero": is_zero,
                "G":G,
                "T":T,
                "Z":Z,
                "f":f,
                "L":L,
            }
        return m
            
            
