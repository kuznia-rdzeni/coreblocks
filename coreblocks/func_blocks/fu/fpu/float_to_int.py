from amaranth import *
from math import log2
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    FPUParams,
    Errors,
    RoundingModes,
    create_data_layout,
)


class FloatToIntMethodLayout:
    """FPU float to int conversion module method layout

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    int_width; int
        Width of result
    """

    def __init__(self, *, fpu_params: FPUParams, int_width: int):
        self.fti_in_layout = [
            ("op", create_data_layout(fpu_params)),
            ("signed", 1),
            ("rounding_mode", RoundingModes),
        ]
        """
        | Input layout for float to int conversion
        | op - layout containing data of the float
            :meth:`create_data_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_data_layout>`
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

    Parameters
    ----------
    fpu_params: FPUParams
        FPU module parameters
    int_width; int
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
            mag_ge_one = Signal()
            at_least_two = op.exp[0 : (self.conv_params.exp_width - 1)].all()
            equal_to_one = op.exp[(self.conv_params.exp_width - 1)]
            m.d.av_comb += mag_ge_one.eq(at_least_two | equal_to_one)

            # Flag indicating if power of base equal to 1/2
            minus_one_exp = Signal()
            bias = Const(2 ** (self.conv_params.exp_width - 1) - 1)
            biased_exp_for_minus_one = Const(bias.value - 1)
            m.d.av_comb += minus_one_exp.eq(op.exp == biased_exp_for_minus_one)

            # Shift for case when mag_ge_one, we assume that number is not big enough
            # to lead to overflow. Maximal value is int_width - 1
            mgeo_shift = Signal(int(log2(self.int_width)) + 1)
            max_shift = Const(self.int_width - 1)
            min_unbiased_exp = 1 - bias.value
            max_unbiased_exp = bias.value
            unbiased_exp = Signal(range(min_unbiased_exp, max_unbiased_exp + 1))
            m.d.av_comb += unbiased_exp.eq(op.exp - bias)
            # +3 is needed to align msb of op.sig with lsb of integer part
            with m.If(unbiased_exp <= max_shift):
                m.d.av_comb += mgeo_shift.eq(unbiased_exp + 2)
            with m.Else():
                m.d.av_comb += mgeo_shift.eq(max_shift + 2)

            # This fixed point number has int_width bits for integer part and
            # sig_width + 1 bits for fractional part
            fixed_point_number = Signal(self.conv_params.sig_width + self.int_width + 1)
            m.d.av_comb += fixed_point_number.eq(
                Mux(mag_ge_one, op.sig << mgeo_shift, Mux(minus_one_exp, op.sig << 1, op.sig))
            )

            sticky_bit = Signal()
            round_bit = Signal()
            inexact = Signal()
            m.d.av_comb += sticky_bit.eq(fixed_point_number[0 : (self.conv_params.sig_width - 1)].any())
            m.d.av_comb += round_bit.eq(fixed_point_number[(self.conv_params.sig_width - 1)])
            m.d.av_comb += inexact.eq(sticky_bit | round_bit)

            # Unrounded (and depending on the sign negated) integer Part of fixed_point_number
            unr_compl_int = Signal(self.int_width)
            integer_part = Signal(self.int_width)
            integer_part_beg = 1 + self.conv_params.sig_width
            integer_part_end = integer_part_beg + self.int_width
            integer_part_slice = fixed_point_number[integer_part_beg:integer_part_end]
            m.d.av_comb += integer_part.eq(integer_part_slice)
            m.d.av_comb += unr_compl_int.eq(Mux(op.sign, ~integer_part, integer_part))

            round_up = Signal()
            with m.Switch(rounding_mode):
                with m.Case(RoundingModes.ROUND_DOWN):
                    m.d.av_comb += round_up.eq(op.sign & inexact)
                with m.Case(RoundingModes.ROUND_NEAREST_AWAY):
                    m.d.av_comb += round_up.eq(round_bit)
                with m.Case(RoundingModes.ROUND_NEAREST_EVEN):
                    tie = fixed_point_number[integer_part_beg] & round_bit
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
            carry_to_msb = Signal()
            m.d.av_comb += carry_to_msb.eq(
                (fixed_point_number[integer_part_beg : integer_part_end - 1].all()) & round_up
            )
            # Macros for some cases that result in out of bound integer
            # Assumptions: magnitude >= 1, output signed, number is positive
            # Out of bounds due to carry or magnitude of input was too big
            sig_pos_out_of_bound = is_max_shift | carry_to_msb
            # Assumptions: magnitude >= 1, output signed, number is negative
            # Input magnitute was too big or it was maximal possible value and
            # we overflowed due to rounding
            sig_neg_out_of_bound = (is_max_shift) & (
                (fixed_point_number[integer_part_beg : integer_part_end - 1].any()) | round_up
            )
            # Assumptions: magnitude >= 1, output unsigned, number is positive
            # Maximal magnitude and carry results in overflow
            un_pos_out_of_bound = is_max_shift & carry_to_msb
            # Assumptions: magnitude < 1
            # In this case we can only get out of bound if we require unsigned number,
            # sign is negative and we need to increase number due to rounding
            mag_bellow_one_out_of_bond = (~signed) & op.sign & round_up

            # Mux when magnitude greater than one and output is signed
            cases_mgeo_osig = Mux(op.sign, sig_neg_out_of_bound, sig_pos_out_of_bound)
            # Mux when magnitude greater than one
            cases_mgeo = Mux(signed, cases_mgeo_osig, (op.sign | un_pos_out_of_bound))
            out_of_bounds = Signal()
            m.d.av_comb += out_of_bounds.eq(
                Mux(mag_ge_one, (unbiased_exp > max_shift) | cases_mgeo, mag_bellow_one_out_of_bond)
            )

            final_sign = Signal()
            m.d.av_comb += final_sign.eq((~op.is_nan) & op.sign)

            invalid_exc = Signal()
            m.d.av_comb += invalid_exc.eq(op.is_inf | op.is_nan | out_of_bounds)

            inexact_exc = Signal()
            m.d.av_comb += inexact_exc.eq((~invalid_exc) & inexact)

            final_integer = Signal(self.int_width)
            errors = Signal(Errors)
            m.d.av_comb += errors.eq(Mux(invalid_exc, Errors.INVALID_OPERATION, Mux(inexact_exc, Errors.INEXACT, 0)))

            with m.If(invalid_exc):
                with m.If(final_sign):
                    with m.If(signed):
                        m.d.av_comb += final_integer.eq(2 ** (self.int_width - 1))
                    with m.Else():
                        m.d.av_comb += final_integer.eq(0)
                with m.Else():
                    with m.If(signed):
                        m.d.av_comb += final_integer.eq(2 ** (self.int_width - 1) - 1)
                    with m.Else():
                        m.d.av_comb += final_integer.eq(2 ** (self.int_width) - 1)
            with m.Else():
                m.d.av_comb += final_integer.eq(integer)

            return {"result": final_integer, "errors": errors}

        return m
