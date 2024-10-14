from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
)


class FPUErrorMethodLayout:
    """FPU error checking module layouts for methods
    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.error_in_layout = [
            ("sign", 1),
            ("sig", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("rounding_mode", RoundingModes),
            ("inexact", 1),
            ("invalid_operation", 1),
            ("division_by_zero", 1),
            ("input_inf", 1),
        ]
        self.error_out_layout = [
            ("sign", 1),
            ("sig", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("errors", 5),
        ]


class FPUErrorModule(Elaboratable):
    """FPU error checking module

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    error_checking_request: Method
        Transactional method for initiating error checking of a floating point number.
        Takes 'error_in_layout' as argument
        Returns final number and errors as 'error_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.fpu_errors_params = fpu_params
        self.method_layouts = FPUErrorMethodLayout(fpu_params=self.fpu_errors_params)
        self.error_checking_request = Method(
            i=self.method_layouts.error_in_layout,
            o=self.method_layouts.error_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        max_exp = C(
            2 ** (self.fpu_errors_params.exp_width) - 1,
            unsigned(self.fpu_errors_params.exp_width),
        )
        max_normal_exp = C(
            2 ** (self.fpu_errors_params.exp_width) - 2,
            unsigned(self.fpu_errors_params.exp_width),
        )
        max_sig = C(
            2 ** (self.fpu_errors_params.sig_width) - 1,
            unsigned(self.fpu_errors_params.sig_width),
        )

        overflow = Signal()
        underflow = Signal()
        inexact = Signal()
        tininess = Signal()

        final_exp = Signal(self.fpu_errors_params.exp_width)
        final_sig = Signal(self.fpu_errors_params.sig_width)
        final_sign = Signal()
        final_errors = Signal(5)

        @def_method(m, self.error_checking_request)
        def _(arg):
            is_nan = arg.invalid_operation | ((arg.exp == max_exp) & (arg.sig.any()))
            is_inf = arg.division_by_zero | arg.input_inf
            input_not_special = ~(is_nan) & ~(is_inf)
            m.d.av_comb += overflow.eq(input_not_special & (arg.exp == max_exp))
            m.d.av_comb += tininess.eq((arg.exp == 0) & (~arg.sig[-1]))
            m.d.av_comb += inexact.eq(overflow | (input_not_special & arg.inexact))
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
                with m.If((arg.exp == 0) & (arg.sig[-1] == 1)):
                    m.d.av_comb += final_exp.eq(1)
                with m.Else():
                    m.d.av_comb += final_exp.eq(arg.exp)
                m.d.av_comb += final_sig.eq(arg.sig)
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
