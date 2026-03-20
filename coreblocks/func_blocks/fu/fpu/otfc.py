from amaranth import *
from transactron import TModule, Method, def_method


class OTFCParams:
    """On the fly conversion function parameters

    Parameters
    ----------
    digit_width: int
        Number of bits of one quotient digit
    result_width: int
        Number of bits of result
    """

    def __init__(
        self,
        *,
        digit_width: int,
        result_width: int,
    ):
        self.digit_width = digit_width
        self.result_width = result_width


class OTFCMethodLayout:
    """Quotient selection function module layouts for methods

    Parameters
    ----------
    otfc_params: OTFCParams
        Parameters of OTFC
    """

    def __init__(self, *, otfc_params: OTFCParams):
        """
        sign - sign of quotient
        q - bits of one quotient digit
        result - result of conversion
        """
        self.otfc_in_layout = [
            ("sign", 1),
            ("q", otfc_params.digit_width),
        ]
        self.otfc_out_layout = [("result", otfc_params.result_width)]


class OTFCModule(Elaboratable):
    """Module for on-the-fly conversion
    TODO

    Parameters
    ----------
    otfc_params: OTFCParams
        Params for OTFC

    Attributes
    ----------
    otfc_add_digit: Method
        Transactional method for adding one digit to result.
        Takes 'otf_in_layout' as argument
    otfc_reset: Method
        Transactional method for reseting state of OTFC
    otfc_result
        Transactinal method for returning result
        Returns result as 'otfc_out_layout'
    """

    def __init__(
        self,
        *,
        otfc_params: OTFCParams,
    ):

        self.otfc_params = otfc_params
        self.method_layouts = OTFCMethodLayout(otfc_params=self.otfc_params)
        self.otfc_add_digit = Method(
            i=self.method_layouts.otfc_in_layout,
            o=[],
        )
        self.otfc_reset = Method(i=[], o=[])
        self.otfc_result = Method(i=[], o=self.method_layouts.otfc_out_layout)

    def elaborate(self, platform):
        m = TModule()
        a_register = Signal(self.otfc_params.result_width)
        b_register = Signal(self.otfc_params.result_width)
        state = Signal(1)

        @def_method(m, self.otfc_result)
        def _(arg):
            return {"result": a_register}

        @def_method(m, self.otfc_reset)
        def _(arg):
            m.d.sync += a_register.eq(0)
            m.d.sync += b_register.eq(0)

        # q = 001'1'1
        # A = 0000
        # B = 1111
        # q = -1 = (1, 01)
        # A' = 1111|11
        # B' = 1111|10
        # A'' = 1111|10|11
        # B'' = 1111|10|10
        # A''' = 1111|10|11|01
        # B''' = 1111|10|11|00
        # (-1) << 4 + (-1) << 2 + 1 = -16 + -4 + 1 = -19
        @def_method(m, self.otfc_add_digit)
        def _(sign, q):
            a1 = q[1] | sign
            a0 = q[0]
            b1 = ((~q[1]) & (~q[0])) | (sign & q[0])
            b0 = ~q[0]

            a_shift = ~sign
            b_shift = (sign) | (q == 0)

            with m.If(a_shift):
                m.d.sync += a_register.eq((a_register << 2) | Cat(a0, a1))
            with m.Else():
                m.d.sync += a_register.eq((b_register << 2) | Cat(a0, a1))

            with m.If(b_shift):
                m.d.sync += b_register.eq((b_register << 2) | Cat(b0, b1))
            with m.Else():
                m.d.sync += b_register.eq((a_register << 2) | Cat(b0, b1))

        return m
