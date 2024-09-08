from amaranth import *
from amaranth.lib.wiring import Component, In, Out, Signature
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    FPURoundingParams,
)


class FPURoundingSignature(Signature):
    """FPU Rounding module signature

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        super().__init__(
            {
                "in_sign": In(1),
                "in_sig": In(fpu_params.sig_width),
                "in_exp": In(fpu_params.exp_width),
                "rounding_mode": In(3),
                "guard_bit": In(1),
                "sticky_bit": In(1),
                "in_errors": In(3),
                "out_sign": In(1),
                "out_sig": Out(fpu_params.sig_width),
                "out_exp": Out(fpu_params.exp_width),
                "out_error": Out(3),
            }
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
            ("guard_bit", 1),
            ("sticky_bit", 1),
            ("rounding_mode", 3),
            ("errors", 5),
            ("input_nan", 1),
            ("input_inf", 1),
        ]
        self.rounding_out_layout = [
            ("sign", 1),
            ("sig", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("errors", 5),
        ]


class FPUrounding(Component):

    fpu_rounding: FPURoundingSignature

    def __init__(self, *, fpu_rounding_params: FPURoundingParams):
        super().__init__({"fpu_rounding": Out(FPURoundingSignature(fpu_params=fpu_rounding_params.fpu_params))})

        self.fpu_rounding_params = fpu_rounding_params
        self.method_layouts = FPURoudningMethodLayout(fpu_params=self.fpu_rounding_params.fpu_params)
        self.rounding_request = Method(
            i=self.method_layouts.rounding_in_layout,
            o=self.method_layouts.rounding_out_layout,
        )
        self.rtval = {}
        self.max_exp = C(
            2 ** (self.fpu_rounding_params.fpu_params.exp_width) - 1,
            unsigned(self.fpu_rounding_params.fpu_params.exp_width),
        )
        self.max_normal_exp = C(
            2 ** (self.fpu_rounding_params.fpu_params.exp_width) - 2,
            unsigned(self.fpu_rounding_params.fpu_params.exp_width),
        )
        self.quiet_nan = C(
            2 ** (self.fpu_rounding_params.fpu_params.sig_width - 1),
            unsigned(self.fpu_rounding_params.fpu_params.sig_width),
        )
        self.max_sig = C(
            2 ** (self.fpu_rounding_params.fpu_params.sig_width) - 1,
            unsigned(self.fpu_rounding_params.fpu_params.sig_width),
        )
        self.add_one = Signal()
        self.inc_rtnte = Signal()
        self.inc_rtnta = Signal()
        self.inc_rtpi = Signal()
        self.inc_rtmi = Signal()

        self.rounded_sig = Signal(self.fpu_rounding_params.fpu_params.sig_width + 1)
        self.normalised_sig = Signal(self.fpu_rounding_params.fpu_params.sig_width)
        self.rounded_exp = Signal(self.fpu_rounding_params.fpu_params.exp_width + 1)

        self.final_guard_bit = Signal()
        self.final_sticky_bit = Signal()

        self.overflow = Signal()
        self.underflow = Signal()
        self.inexact = Signal()
        self.tininess = Signal()
        self.is_inf = Signal()
        self.is_nan = Signal()
        self.input_not_special = Signal()
        self.rounded_inexact = Signal()

        self.final_exp = Signal(self.fpu_rounding_params.fpu_params.exp_width)
        self.final_sig = Signal(self.fpu_rounding_params.fpu_params.sig_width)
        self.final_sign = Signal()
        self.final_errors = Signal(5)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.rounding_request)
        def _(arg):

            m.d.comb += self.inc_rtnte.eq(
                (arg.rounding_mode == RoundingModes.ROUND_NEAREST_EVEN)
                & (arg.guard_bit & (arg.sticky_bit | arg.sig[0]))
            )
            m.d.comb += self.inc_rtnta.eq((arg.rounding_mode == RoundingModes.ROUND_NEAREST_AWAY) & (arg.guard_bit))
            m.d.comb += self.inc_rtpi.eq(
                (arg.rounding_mode == RoundingModes.ROUND_UP) & (~arg.sign & (arg.guard_bit | arg.sticky_bit))
            )
            m.d.comb += self.inc_rtmi.eq(
                (arg.rounding_mode == RoundingModes.ROUND_DOWN) & (arg.sign & (arg.guard_bit | arg.sticky_bit))
            )

            m.d.comb += self.add_one.eq(self.inc_rtmi | self.inc_rtnta | self.inc_rtnte | self.inc_rtpi)

            if self.fpu_rounding_params.is_rounded:

                m.d.comb += self.normalised_sig.eq(arg.sig)
                m.d.comb += self.final_guard_bit.eq(arg.guard_bit)
                m.d.comb += self.final_sticky_bit.eq(arg.sticky_bit)
                m.d.comb += self.rounded_exp.eq(arg.exp)

            else:

                m.d.comb += self.rounded_sig.eq(arg.sig + self.add_one)

                with m.If(self.rounded_sig[-1]):

                    m.d.comb += self.normalised_sig.eq(self.rounded_sig >> 1)
                    m.d.comb += self.final_guard_bit.eq(self.rounded_sig[0])
                    m.d.comb += self.final_sticky_bit.eq(arg.guard_bit | arg.sticky_bit)
                    m.d.comb += self.rounded_exp.eq(arg.exp + 1)

                with m.Else():
                    m.d.comb += self.normalised_sig.eq(self.rounded_sig)
                    m.d.comb += self.final_guard_bit.eq(arg.guard_bit)
                    m.d.comb += self.final_sticky_bit.eq(arg.sticky_bit)
                    m.d.comb += self.rounded_exp.eq(arg.exp)

            m.d.comb += self.rounded_inexact.eq(self.final_guard_bit | self.final_sticky_bit)
            m.d.comb += self.is_nan.eq(arg.errors[0] | arg.input_nan)
            m.d.comb += self.is_inf.eq(arg.errors[1] | arg.input_inf)
            m.d.comb += self.input_not_special.eq(~(self.is_nan) & ~(self.is_inf))
            m.d.comb += self.overflow.eq(self.input_not_special & (self.rounded_exp >= self.max_exp))
            m.d.comb += self.tininess.eq(
                (self.rounded_exp == 0) & (self.rounded_inexact | self.rounded_sig.any()) & (~self.normalised_sig[-1])
            )
            m.d.comb += self.inexact.eq(self.overflow | (self.input_not_special & self.rounded_inexact))
            m.d.comb += self.underflow.eq(self.tininess & self.inexact)

            with m.If(self.is_nan):

                m.d.comb += self.final_exp.eq(self.max_exp)
                m.d.comb += self.final_sig.eq(arg.sig)
                m.d.comb += self.final_sign.eq(arg.sign)

            with m.Elif(self.is_inf):

                m.d.comb += self.final_exp.eq(self.max_exp)
                m.d.comb += self.final_sig.eq(arg.sig)
                m.d.comb += self.final_sign.eq(arg.sign)

            with m.Elif(self.overflow):

                with m.If(
                    (arg.rounding_mode == RoundingModes.ROUND_NEAREST_AWAY)
                    | (arg.rounding_mode == RoundingModes.ROUND_NEAREST_EVEN)
                ):

                    m.d.comb += self.final_exp.eq(self.max_exp)
                    m.d.comb += self.final_sig.eq(0)
                    m.d.comb += self.final_sign.eq(arg.sign)

                with m.If(arg.rounding_mode == RoundingModes.ROUND_ZERO):

                    m.d.comb += self.final_exp.eq(self.max_normal_exp)
                    m.d.comb += self.final_sig.eq(self.max_sig)
                    m.d.comb += self.final_sign.eq(arg.sign)

                with m.If(arg.rounding_mode == RoundingModes.ROUND_DOWN):

                    with m.If(arg.sign):

                        m.d.comb += self.final_exp.eq(self.max_exp)
                        m.d.comb += self.final_sig.eq(0)
                        m.d.comb += self.final_sign.eq(arg.sign)

                    with m.Else():

                        m.d.comb += self.final_exp.eq(self.max_normal_exp)
                        m.d.comb += self.final_sig.eq(self.max_sig)
                        m.d.comb += self.final_sign.eq(arg.sign)

                with m.If(arg.rounding_mode == RoundingModes.ROUND_UP):

                    with m.If(arg.sign):

                        m.d.comb += self.final_exp.eq(self.max_normal_exp)
                        m.d.comb += self.final_sig.eq(self.max_sig)
                        m.d.comb += self.final_sign.eq(arg.sign)

                    with m.Else():

                        m.d.comb += self.final_exp.eq(self.max_exp)
                        m.d.comb += self.final_sig.eq(0)
                        m.d.comb += self.final_sign.eq(arg.sign)

            with m.Else():
                with m.If((self.rounded_exp == 0) & (self.normalised_sig[-1] == 1)):
                    m.d.comb += self.final_exp.eq(1)
                with m.Else():
                    m.d.comb += self.final_exp.eq(self.rounded_exp)
                m.d.comb += self.final_sig.eq(self.normalised_sig)
                m.d.comb += self.final_sign.eq(arg.sign)

            m.d.comb += self.final_errors[0].eq(arg.errors[0])
            m.d.comb += self.final_errors[1].eq(arg.errors[1])
            m.d.comb += self.final_errors[2].eq(self.overflow)
            m.d.comb += self.final_errors[3].eq(self.underflow)
            m.d.comb += self.final_errors[4].eq(self.inexact)

            self.rtval["exp"] = self.final_exp
            self.rtval["sig"] = self.final_sig
            self.rtval["sign"] = self.final_sign
            self.rtval["errors"] = self.final_errors

            return self.rtval

        return m
