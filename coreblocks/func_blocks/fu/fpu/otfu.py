from amaranth import *
from transactron import TModule, Method, def_method


class OTFUParams:
    """On-the-fly update function parameters

    Parameters
    ----------
    result_width: int
        Number of bits of result
    """

    def __init__(
        self,
        *,
        result_width: int,
    ):
        self.result_width = result_width


class OTFUMethodLayout:
    """On-the-fly update function module layouts for methods

    Parameters
    ----------
    otfu_params: OTFUParams
        Parameters of OTFU
    """

    def __init__(self, *, otfu_params: OTFUParams):
        """
        sign - sign of one root digit
        q - bits of one root digit
        result - result width of conversion
        """
        self.otfu_add_digit_in_layout = [
            ("sign", 1),
            ("q", 1),
        ]
        self.otfu_result_out_layout = [
            ("f_one", 2 + otfu_params.result_width),
            ("f_m_one", 2 + otfu_params.result_width),
        ]


class OTFUModule(Elaboratable):
    """Module for on-the-fly update
    This module is responsible for updating F1 and F-1 needed to update residual of square root.
    The module functions similar to OTFC (on-the-fly conversion) but rather than computing
    result (one number) in non redundant form, this module computes values of F
    which is a formula rather than one number, thus the process is a little bit more complex.
    The formulas comes from "Digital Arithmetic" by Milos D. Ercegovac and Tomas Lang
    Parameters
    ----------
    otfu_params: OTFUParams
        Params for OTFU

    Attributes
    ----------
    otfu_add_digit: Method
        Transactional method for adding one digit to result
        Takes 'otfu_add_digit_in_layout' as argument
    otfu_reset: Method
        Transactional method for reseting state of OTFU
    otfu_result
        Transactinal method for returning result
        Takes 'otfu_result_in_layout as argument'
        Returns result as 'otfu_result_out_layout'
    """

    def __init__(
        self,
        *,
        otfu_params: OTFUParams,
    ):

        self.otfu_params = otfu_params
        self.method_layouts = OTFUMethodLayout(otfu_params=self.otfu_params)
        self.otfu_add_digit = Method(
            i=self.method_layouts.otfu_add_digit_in_layout,
            o=[],
        )
        self.otfu_reset = Method(i=[], o=[])
        self.otfu_result = Method(
            o=self.method_layouts.otfu_result_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()
        additional_int_bits = 2
        f_one = Signal(self.otfu_params.result_width + additional_int_bits)
        f_m_one = Signal(self.otfu_params.result_width + additional_int_bits)
        k = Signal(self.otfu_params.result_width + additional_int_bits)
        one_pattern = Signal(self.otfu_params.result_width + additional_int_bits)
        zero_pattern = Signal(self.otfu_params.result_width + additional_int_bits)

        @def_method(m, self.otfu_result)
        def _():
            return {"f_one": f_one, "f_m_one": f_m_one}

        @def_method(m, self.otfu_reset)
        def _(arg):
            f_shift = self.otfu_params.result_width + additional_int_bits - 4
            k_shift = self.otfu_params.result_width + additional_int_bits - 2
            patterns_shift = self.otfu_params.result_width + additional_int_bits - 3 - 2

            m.d.sync += f_one.eq(15 << f_shift)
            m.d.sync += f_m_one.eq(15 << f_shift)
            m.d.sync += k.eq(3 << k_shift)
            m.d.sync += one_pattern.eq(3 << patterns_shift)
            m.d.sync += zero_pattern.eq(7 << patterns_shift)

        @def_method(m, self.otfu_add_digit)
        def _(sign, q):
            k_update_bit = 1 << (self.otfu_params.result_width + additional_int_bits - 1)
            with m.If(q == 1):
                with m.If(sign == 0):
                    m.d.sync += f_one.eq((f_one & k) | one_pattern)
                    m.d.sync += f_m_one.eq(((~f_one) & k) | one_pattern)
                with m.Else():
                    m.d.sync += f_one.eq(((~f_m_one) & k) | one_pattern)
                    m.d.sync += f_m_one.eq((f_m_one & k) | one_pattern)
            with m.Else():
                m.d.sync += f_one.eq((f_one & k) | zero_pattern)
                m.d.sync += f_m_one.eq((f_m_one & k) | zero_pattern)
            m.d.sync += k.eq((k >> 1) | k_update_bit)
            m.d.sync += one_pattern.eq(one_pattern >> 1)
            m.d.sync += zero_pattern.eq(zero_pattern >> 1)

        return m
