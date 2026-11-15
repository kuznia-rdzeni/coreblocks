from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    FPUParams,
    Errors,
    RoundingModes,
    create_data_input_layout,
)


class FloatToIntMethodLayout:
    """FPU float to int conversion module method layout

    Parameters
    ----------
    fpu_params: FPUParams
        FPU parameters
    int_width: int
        Width of result
    """

    def __init__(self, *, fpu_params: FPUParams, int_width: int):
        self.fti_in_layout = [
            ("op", create_data_input_layout(fpu_params)),
            ("signed", 1),
            ("rounding_mode", RoundingModes),
        ]
        """
        | Input layout for float to int conversion
        | op - layout containing data of the float
            :meth:`create_data_input_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_data_input_layout>`
        | signed - bit indicating if result is signed or unsigned
        | rounding_mode - selected rounding mode
        """
        self.fti_out_layout = {("result", int_width), ("errors", Errors)}
        """
        | Output layout for comparision created using
        | result - result of the conversion
        | errors - exceptions
        """


class FloatToIntModule(Elaboratable):
    """Module for float to int conversion
    Module responsible for performing conversion from float to int.
    This module doesn't extend 32 bit number when XLEN > 32

    Parameters
    ----------
    fpu_params: FPUParams
        FPU module parameters
    int_width: int
        Width of the result

    Attributes
    ----------
    fti_request: Method
        Transactional method for initiating conversion.
        Takes 'fti_in_layout' as argument
        Returns result as 'fti_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams, int_width: int):

        self.conv_params = fpu_params
        self.int_width = int_width
        self.method_layouts = FloatToIntMethodLayout(fpu_params=self.conv_params, int_width=self.int_width)
        self.fti_request = Method(
            i=self.method_layouts.fti_in_layout,
            o=self.method_layouts.fti_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.fti_request)
        def _(op, signed, rounding_mode):
            # Flag indicating if magnitude is greater or equal one
            bias = 2 ** (self.conv_params.exp_width - 1) - 1
            mag_ge_one = Signal()
            # Check if exp is equal to 2^0
            # Check if exp is ge than 2^1
            m.d.av_comb += mag_ge_one.eq(op.exp >= bias)

            # Flag indicating if power of base equal to 1/2
            minus_one_exp = Signal()
            m.d.av_comb += minus_one_exp.eq(op.exp == (bias - 1))

            # Shift for case when mag_ge_one, we assume that number is not big enough
            # to lead to overflow. Maximal value is int_width - 1
            alignment_shift = 2
            max_shift = self.int_width - 1
            mgeo_shift = Signal(range(0, max_shift + alignment_shift + 1))
            min_unbiased_exp = 1 - bias
            max_unbiased_exp = bias
            unbiased_exp = Signal(range(min_unbiased_exp, max_unbiased_exp + 1))
            # We can ignore subnormal in this case
            m.d.av_comb += unbiased_exp.eq(op.exp - bias)
            # +2 is needed to align the only integer bit of op.sig with lsb of integer part
            # of out fixed point number
            with m.If(unbiased_exp < -1):
                m.d.av_comb += mgeo_shift.eq(0)
            with m.Elif(unbiased_exp <= max_shift):
                m.d.av_comb += mgeo_shift.eq(unbiased_exp + alignment_shift)
            with m.Else():
                m.d.av_comb += mgeo_shift.eq(max_shift + alignment_shift)

            # This fixed point number has int_width bits for integer part and
            # sig_width + 1 bits for fractional part
            # the sig_width LSB serve as a sort of bin that keeps sticky bits
            # This is why we have separate case for 2^(-1), it is the only case
            # of exp power less than zero that produces round bit
            fractional_part_length = self.conv_params.sig_width + 1
            fixed_point_number = Signal(fractional_part_length + self.int_width)
            m.d.av_comb += fixed_point_number.eq(op.sig << mgeo_shift)

            fractional_part = Signal(fractional_part_length)
            m.d.av_comb += fractional_part.eq(fixed_point_number)
            integer_part = Signal(self.int_width)
            m.d.av_comb += integer_part.eq(fixed_point_number >> fractional_part_length)

            sticky_bit = Signal()
            round_bit = Signal()
            inexact = Signal()
            m.d.av_comb += sticky_bit.eq(fractional_part[:-1].any())
            m.d.av_comb += round_bit.eq(fractional_part[-1])
            m.d.av_comb += inexact.eq(sticky_bit | round_bit)

            # Unrounded (and depending on the sign negated) integer Part of fixed_point_number
            unr_compl_int = Signal(self.int_width)
            m.d.av_comb += unr_compl_int.eq(Mux(op.sign, ~integer_part, integer_part))

            round_up = Signal()
            with m.Switch(rounding_mode):
                with m.Case(RoundingModes.ROUND_DOWN):
                    m.d.av_comb += round_up.eq(op.sign & inexact)
                with m.Case(RoundingModes.ROUND_NEAREST_AWAY):
                    m.d.av_comb += round_up.eq(round_bit)
                with m.Case(RoundingModes.ROUND_NEAREST_EVEN):
                    tie = integer_part[0] & round_bit
                    above_halfway = round_bit & sticky_bit
                    m.d.av_comb += round_up.eq(tie | above_halfway)
                with m.Case(RoundingModes.ROUND_UP):
                    m.d.av_comb += round_up.eq((~op.sign) & inexact)
                with m.Case(RoundingModes.ROUND_ZERO):
                    m.d.av_comb += round_up.eq(0)

            increment = Signal()
            integer = Signal(self.int_width)
            # The rounding is applied to our fixed point number (absolute value of integer),
            # thus if we have to both complement and round up we can just negate our number
            # without adding anything
            m.d.av_comb += increment.eq(round_up ^ op.sign)
            m.d.av_comb += integer.eq(unr_compl_int + increment)

            # This part checks if we are out of bounds because input was to large
            # Maximum possible shift that might not result in overflow
            is_max_shift = Signal()
            m.d.av_comb += is_max_shift.eq(unbiased_exp == max_shift)
            # We check if carry propagated to msb bit, important for
            # signed integers
            carry_to_msb = Signal()
            m.d.av_comb += carry_to_msb.eq((integer_part[:-1].all()) & round_up)
            # Macros for some cases that result in out of bound integer
            # Assumptions: magnitude >= 1, output signed, number is positive
            # Out of bounds due to carry or magnitude of input was too big
            sig_pos_out_of_bound = is_max_shift | carry_to_msb
            # Assumptions: magnitude >= 1, output signed, number is negative
            # Input magnitute was too big or it was maximal possible value and
            # we overflowed due to rounding
            sig_neg_out_of_bound = (is_max_shift) & ((integer_part[:-1].any()) | round_up)
            # Assumptions: magnitude >= 1, output unsigned, number is positive
            # Maximal magnitude and carry results in overflow
            un_pos_out_of_bound = is_max_shift & carry_to_msb
            # Assumptions: magnitude < 1
            # In this case we can only get out of bound if we require unsigned number,
            # sign is negative and we need to increase number due to rounding
            mag_bellow_one_out_of_bound = (~signed) & op.sign & round_up

            # Mux when magnitude greater than one and output is signed
            cases_mgeo_osig = Mux(op.sign, sig_neg_out_of_bound, sig_pos_out_of_bound)
            # Mux when magnitude greater than one
            cases_mgeo = Mux(signed, cases_mgeo_osig, (op.sign | un_pos_out_of_bound))
            out_of_bounds = Signal()
            m.d.av_comb += out_of_bounds.eq(
                Mux(
                    mag_ge_one,
                    (unbiased_exp > max_shift) | cases_mgeo,
                    mag_bellow_one_out_of_bound,
                )
            )

            final_sign = Signal()
            m.d.av_comb += final_sign.eq((~op.is_nan) & op.sign)

            invalid_exc = Signal()
            m.d.av_comb += invalid_exc.eq(op.is_inf | op.is_nan | out_of_bounds)

            inexact_exc = Signal()
            m.d.av_comb += inexact_exc.eq((~invalid_exc) & inexact)

            final_integer = Signal(self.int_width)
            errors = Signal(Errors)
            m.d.av_comb += errors.eq(
                Mux(
                    invalid_exc,
                    Errors.INVALID_OPERATION,
                    Mux(inexact_exc, Errors.INEXACT, 0),
                )
            )

            smallest_us_value = Const(0)
            biggest_us_value = Const(2 ** (self.int_width) - 1)
            smallest_s_value = Const(2 ** (self.int_width - 1))
            biggest_s_value = Const(2 ** (self.int_width - 1) - 1)

            mux_pos = Mux(signed, biggest_s_value, biggest_us_value)
            mux_neg = Mux(signed, smallest_s_value, smallest_us_value)
            mux_invalid_exc = Mux(final_sign, mux_neg, mux_pos)

            m.d.av_comb += final_integer.eq(Mux(invalid_exc, mux_invalid_exc, integer))

            return {"result": final_integer, "errors": errors}

        return m
