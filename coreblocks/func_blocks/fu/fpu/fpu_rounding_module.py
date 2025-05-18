from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
)


class FPURoudningMethodLayout:
    """FPU Rounding module layouts for methods

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.rounding_in_layout = [
            ("sign", 1),
            ("sig", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("round_bit", 1),
            ("sticky_bit", 1),
            ("rounding_mode", RoundingModes),
        ]
        self.rounding_out_layout = [
            ("sig", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("inexact", 1),
        ]


class FPURounding(Elaboratable):
    """FPU Rounding module

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters

    Attributes
    ----------
    rounding_request: Method
        Transactional method for initiating rounding of a floating point number.
        Takes 'rounding_in_layout' as argument
        Returns rounded number and errors as 'rounding_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.fpu_rounding_params = fpu_params
        self.method_layouts = FPURoudningMethodLayout(fpu_params=self.fpu_rounding_params)
        self.rounding_request = Method(
            i=self.method_layouts.rounding_in_layout,
            o=self.method_layouts.rounding_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        add_one = Signal()
        inc_rtnte = Signal()
        inc_rtnta = Signal()
        inc_rtpi = Signal()
        inc_rtmi = Signal()

        rounded_sig = Signal(self.fpu_rounding_params.sig_width + 1)
        normalised_sig = Signal(self.fpu_rounding_params.sig_width)
        rounded_exp = Signal(self.fpu_rounding_params.exp_width)

        final_round_bit = Signal()
        final_sticky_bit = Signal()

        inexact = Signal()

        @def_method(m, self.rounding_request)
        def _(arg):

            m.d.av_comb += inc_rtnte.eq(
                (arg.rounding_mode == RoundingModes.ROUND_NEAREST_EVEN)
                & (arg.round_bit & (arg.sticky_bit | arg.sig[0]))
            )
            m.d.av_comb += inc_rtnta.eq((arg.rounding_mode == RoundingModes.ROUND_NEAREST_AWAY) & (arg.round_bit))
            m.d.av_comb += inc_rtpi.eq(
                (arg.rounding_mode == RoundingModes.ROUND_UP) & (~arg.sign & (arg.round_bit | arg.sticky_bit))
            )
            m.d.av_comb += inc_rtmi.eq(
                (arg.rounding_mode == RoundingModes.ROUND_DOWN) & (arg.sign & (arg.round_bit | arg.sticky_bit))
            )

            m.d.av_comb += add_one.eq(inc_rtmi | inc_rtnta | inc_rtnte | inc_rtpi)

            m.d.av_comb += rounded_sig.eq(arg.sig + add_one)

            with m.If(rounded_sig[-1]):

                m.d.av_comb += normalised_sig.eq(rounded_sig >> 1)
                m.d.av_comb += final_round_bit.eq(rounded_sig[0])
                m.d.av_comb += final_sticky_bit.eq(arg.round_bit | arg.sticky_bit)
                m.d.av_comb += rounded_exp.eq(arg.exp + 1)

            with m.Else():
                m.d.av_comb += normalised_sig.eq(rounded_sig)
                m.d.av_comb += final_round_bit.eq(arg.round_bit)
                m.d.av_comb += final_sticky_bit.eq(arg.sticky_bit)
                m.d.av_comb += rounded_exp.eq(arg.exp)

            m.d.av_comb += inexact.eq(final_round_bit | final_sticky_bit)

            return {
                "exp": rounded_exp,
                "sig": normalised_sig,
                "inexact": inexact,
            }

        return m
