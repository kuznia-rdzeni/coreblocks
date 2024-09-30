from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    FPURoundingParams,
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
            ("rounding_mode", Shape.cast(RoundingModes)),
            ("invalid_operation", 1),
            ("division_by_zero", 1),
            ("input_inf", 1),
        ]
        self.rounding_out_layout = [
            ("sign", 1),
            ("sig", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("errors", 5),
        ]


class FPUrounding(Elaboratable):
    """FPU Rounding module

    Parameters
    ----------
    fpu_rounding_params: FPURoundingParams
        FPU rounding module parameters

    Attributes
    ----------
    rounding_request: Method
        Transactional method for initiating rounding of a floating point number.
        Takes 'rounding_in_layout' as argument
        Returns rounded number and errors as 'rounding_out_layout'
    """

    def __init__(self, *, fpu_rounding_params: FPURoundingParams):

        self.fpu_rounding_params = fpu_rounding_params
        self.method_layouts = FPURoudningMethodLayout(fpu_params=self.fpu_rounding_params.fpu_params)
        self.rounding_request = Method(
            i=self.method_layouts.rounding_in_layout,
            o=self.method_layouts.rounding_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        max_exp = C(
            2 ** (self.fpu_rounding_params.fpu_params.exp_width) - 1,
            unsigned(self.fpu_rounding_params.fpu_params.exp_width),
        )
        max_normal_exp = C(
            2 ** (self.fpu_rounding_params.fpu_params.exp_width) - 2,
            unsigned(self.fpu_rounding_params.fpu_params.exp_width),
        )
        max_sig = C(
            2 ** (self.fpu_rounding_params.fpu_params.sig_width) - 1,
            unsigned(self.fpu_rounding_params.fpu_params.sig_width),
        )
        add_one = Signal()
        inc_rtnte = Signal()
        inc_rtnta = Signal()
        inc_rtpi = Signal()
        inc_rtmi = Signal()

        rounded_sig = Signal(self.fpu_rounding_params.fpu_params.sig_width + 1)
        normalised_sig = Signal(self.fpu_rounding_params.fpu_params.sig_width)
        rounded_exp = Signal(self.fpu_rounding_params.fpu_params.exp_width + 1)

        final_round_bit = Signal()
        final_sticky_bit = Signal()

        overflow = Signal()
        underflow = Signal()
        inexact = Signal()
        tininess = Signal()

        final_exp = Signal(self.fpu_rounding_params.fpu_params.exp_width)
        final_sig = Signal(self.fpu_rounding_params.fpu_params.sig_width)
        final_sign = Signal()
        final_errors = Signal(5)

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

            if self.fpu_rounding_params.is_rounded:

                m.d.av_comb += normalised_sig.eq(arg.sig)
                m.d.av_comb += final_round_bit.eq(arg.round_bit)
                m.d.av_comb += final_sticky_bit.eq(arg.sticky_bit)
                m.d.av_comb += rounded_exp.eq(arg.exp)

            else:

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

            rounded_inexact = final_round_bit | final_sticky_bit
            is_nan = arg.invalid_operation | ((arg.exp == max_exp) & (arg.sig.any()))
            is_inf = arg.division_by_zero | arg.input_inf
            input_not_special = ~(is_nan) & ~(is_inf)
            m.d.av_comb += overflow.eq(input_not_special & (rounded_exp >= max_exp))
            m.d.av_comb += tininess.eq((rounded_exp == 0) & (~normalised_sig[-1]))
            m.d.av_comb += inexact.eq(overflow | (input_not_special & rounded_inexact))
            m.d.av_comb += underflow.eq(tininess & inexact)

            with m.If(is_nan | is_inf):

                m.d.av_comb += final_exp.eq(arg.exp)
                m.d.av_comb += final_sig.eq(arg.sig)
                m.d.av_comb += final_sign.eq(arg.sign)

            with m.Elif(overflow):

                with m.Switch(arg.rounding_mode):
                    with m.Case(RoundingModes.ROUND_NEAREST_AWAY, RoundingModes.ROUND_NEAREST_EVEN):

                        m.d.av_comb += final_exp.eq(max_exp)
                        m.d.av_comb += final_sig.eq(0)
                        m.d.av_comb += final_sign.eq(arg.sign)

                    with m.Case(RoundingModes.ROUND_ZERO):

                        m.d.av_comb += final_exp.eq(max_normal_exp)
                        m.d.av_comb += final_sig.eq(max_sig)
                        m.d.av_comb += final_sign.eq(arg.sign)

                    with m.Case(RoundingModes.ROUND_DOWN):

                        with m.If(arg.sign):

                            m.d.av_comb += final_exp.eq(max_exp)
                            m.d.av_comb += final_sig.eq(0)
                            m.d.av_comb += final_sign.eq(arg.sign)

                        with m.Else():

                            m.d.av_comb += final_exp.eq(max_normal_exp)
                            m.d.av_comb += final_sig.eq(max_sig)
                            m.d.av_comb += final_sign.eq(arg.sign)

                    with m.Case(RoundingModes.ROUND_UP):

                        with m.If(arg.sign):

                            m.d.av_comb += final_exp.eq(max_normal_exp)
                            m.d.av_comb += final_sig.eq(max_sig)
                            m.d.av_comb += final_sign.eq(arg.sign)

                        with m.Else():

                            m.d.av_comb += final_exp.eq(max_exp)
                            m.d.av_comb += final_sig.eq(0)
                            m.d.av_comb += final_sign.eq(arg.sign)

            with m.Else():
                with m.If((rounded_exp == 0) & (normalised_sig[-1] == 1)):
                    m.d.av_comb += final_exp.eq(1)
                with m.Else():
                    m.d.av_comb += final_exp.eq(rounded_exp)
                m.d.av_comb += final_sig.eq(normalised_sig)
                m.d.av_comb += final_sign.eq(arg.sign)

            m.d.av_comb += final_errors[0].eq(arg.invalid_operation)
            m.d.av_comb += final_errors[1].eq(arg.division_by_zero)
            m.d.av_comb += final_errors[2].eq(overflow)
            m.d.av_comb += final_errors[3].eq(underflow)
            m.d.av_comb += final_errors[4].eq(inexact)

            return {
                "exp": final_exp,
                "sig": final_sig,
                "sign": final_sign,
                "errors": final_errors,
            }

        return m
