from amaranth import *
from amaranth.lib import enum
from transactron import TModule, Method, def_method


class DigitWidth(enum.IntFlag):
    WIDTH_ONE = 1
    WIDTH_TWO = 2


class OTFCParams:
    """On-the-fly conversion function parameters

    Parameters
    ----------
    result_width: int
        Number of bits of result
    digit_width: DigitWidth
        Width of digit
    """

    def __init__(self, *, result_width: int, digit_width: DigitWidth):
        self.result_width = result_width
        self.digit_width = digit_width


class OTFCMethodLayout:
    """On-the-fly conversion function module layouts for methods

    Parameters
    ----------
    otfc_params: OTFCParams
        Parameters of OTFC
    """

    def __init__(self, *, otfc_params: OTFCParams):
        """
        sign - sign of quotient
        q - bits of one quotient digit
        shift - last shift before returning result, mostly needed in case of zero remainder termination
        result - result of conversion
        """
        self.otfc_add_digit_in_layout = [
            ("sign", 1),
            ("q", otfc_params.digit_width),
        ]
        self.otfc_result_in_layout = [
            (
                "shift",
                range(0, otfc_params.digit_width + otfc_params.result_width + 1),
            )
        ]
        self.otfc_result_out_layout = [("result", otfc_params.digit_width.value + otfc_params.result_width)]


class OTFCModule(Elaboratable):
    """Module for on-the-fly conversion
    This module performs on-the-fly-conversion for SRT radix 4 with redundant set where a = 2.
    Algorithm works by keeping two registers, one assuming next digit is nonnegative and the
    other one otherwise, to deal with carry propagation.
    Algorithm taken from "Digital arithmetic" by Miloš D. Ercegovac and Tomás Lang.

    Parameters
    ----------
    otfc_params: OTFCParams
        Params for OTFC

    Attributes
    ----------
    otfc_add_digit: Method
        Transactional method for adding one digit to result
        Takes 'otfc_add_digit_in_layout' as argument
    otfc_reset: Method
        Transactional method for reseting state of OTFC
    otfc_result
        Transactinal method for returning result
        Takes 'otfc_result_in_layout as argument'
        Returns result as 'otfc_result_out_layout'
    """

    def __init__(
        self,
        *,
        otfc_params: OTFCParams,
    ):

        self.otfc_params = otfc_params
        self.method_layouts = OTFCMethodLayout(otfc_params=self.otfc_params)
        self.otfc_add_digit = Method(
            i=self.method_layouts.otfc_add_digit_in_layout,
            o=[],
        )
        self.otfc_reset = Method(i=[], o=[])
        self.otfc_result = Method(
            i=self.method_layouts.otfc_result_in_layout,
            o=self.method_layouts.otfc_result_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()
        a_register = Signal(self.otfc_params.digit_width + self.otfc_params.result_width)
        b_register = Signal(self.otfc_params.digit_width + self.otfc_params.result_width)
        a = Signal(self.otfc_params.digit_width)
        b = Signal(self.otfc_params.digit_width)

        @def_method(m, self.otfc_result)
        def _(shift):
            return {"result": a_register << shift}

        @def_method(m, self.otfc_reset)
        def _(arg):
            m.d.sync += a_register.eq(0)
            m.d.sync += b_register.eq((2 ** (self.otfc_params.digit_width)) - 1)

        @def_method(m, self.otfc_add_digit)
        def _(sign, q):
            if self.otfc_params.digit_width == DigitWidth.WIDTH_TWO:
                a1 = q[1] | sign
                a0 = q[0]
                b1 = ((~q[1]) & (~q[0])) | (sign & q[0])
                b0 = ~q[0]
                a_shift = ~sign
                b_shift = (sign) | (q == 0)
                m.d.comb += a.eq((a1 << 1) | a0)
                m.d.comb += b.eq((b1 << 1) | b0)
            elif self.otfc_params.digit_width == DigitWidth.WIDTH_ONE:
                m.d.comb += a.eq(q)
                m.d.comb += b.eq(q == 0)
                a_shift = ~sign
                b_shift = (sign) | (q == 0)
            with m.If(a_shift):
                m.d.sync += a_register.eq((a_register << self.otfc_params.digit_width) | a)
            with m.Else():
                m.d.sync += a_register.eq((b_register << self.otfc_params.digit_width) | a)

            with m.If(b_shift):
                m.d.sync += b_register.eq((b_register << self.otfc_params.digit_width) | b)
            with m.Else():
                m.d.sync += b_register.eq((a_register << self.otfc_params.digit_width) | b)

        return m
