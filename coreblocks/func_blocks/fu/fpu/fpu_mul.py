from amaranth import *
from transactron import TModule, Method, def_method
from transactron.utils.transactron_helpers import from_method_layout
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    create_data_input_layout,
    create_output_layout,
    FPUCommonValues,
)
from coreblocks.func_blocks.fu.fpu.fpu_error_module import FPUErrorModule
from coreblocks.func_blocks.fu.fpu.fpu_rounding_module import FPURounding
from transactron.utils.amaranth_ext import count_leading_zeros
from coreblocks.func_blocks.fu.unsigned_multiplication.fast_recursive import FastRecursiveMul


class FPUMulMethodLayout:
    """FPU multiplication module method layout

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.mul_in_layout = [
            ("op_1", create_data_input_layout(fpu_params)),
            ("op_2", create_data_input_layout(fpu_params)),
            ("rounding_mode", RoundingModes),
        ]
        """
        | Input layout for multiplication
        | op_1 - layout containing data of the first operand
        | op_2 - layout containing data of the second operand
        | rounding_mode - selected rounding mode
        | op_1 and op_2 are created using
          :meth:`create_data_input_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_data_input_layout>`
        """
        self.mul_out_layout = create_output_layout(fpu_params)
        """
        Output layout for multiplication. Created using
        :meth:`create_output_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_output_layout>`
        """


class FPUMulModule(Elaboratable):
    """
    | FPU multiplication top module
    | The floating point multiplication consists of two parts:
    | 1. Exponent calcuation - turning both exponents from biased form into un-biased form
    | and then adding them together and turing result back into biased form
    | 2. Significand multiplication - This is essentialy fixed-point multiplication with
    | two bits for integer part and 2*n - 2 bits for fractional part.
    | We deal with with subnormal number by extending exponents range and turning subnormal
    | numbers into normalised numbers.  

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    mul_request: Method
        Transactional method for initiating multiplication.
        Takes
        :meth:`mul_in_layout <coreblocks.func_blocks.fu.fpu.fpu_add_sub.FPUMulMethodLayout.add_sub_in_layout>`
        as argument.
        Returns result as
        :meth:`mul_out_layout <coreblocks.func_blocks.fu.fpu.fpu_add_sub.FPUMulMethodLayout.add_sub_out_layout>`.
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.fpu_params = fpu_params
        self.method_layouts = FPUMulMethodLayout(fpu_params=self.fpu_params)
        self.common_values = FPUCommonValues(self.fpu_params)
        self.mul_request = Method(
            i=self.method_layouts.mul_in_layout,
            o=self.method_layouts.mul_out_layout,
        )
        self.mul_params = {"isa":{"xlen":self.fpu_params.sig_width}}

    def elaborate(self, platform):
        m = TModule()

        m.submodules.rounding_module = rounding_module = FPURounding(fpu_params=self.fpu_params)
        m.submodules.exception_module = exception_module = FPUErrorModule(fpu_params=self.fpu_params)
        m.submodules.multiplier = multiplier = FastRecursiveMul(self.fpu_params.sig_width,self.fpu_params.sig_width//2)

        rounding_response = Signal(from_method_layout(rounding_module.method_layouts.rounding_out_layout))
        exception_response = Signal(from_method_layout(exception_module.method_layouts.error_out_layout))

        bias = self.common_values.bias
        min_real_exp = 1 - (2 ** (bias - 1))

        @def_method(m, self.mul_request)
        def _(op_1, op_2, rounding_mode):

            final_sign = Signal()
            m.d.av_comb += final_sign.eq(op_1.sign ^ op_2.sign)
            op_1_subn = ~op_1.sig[-1]
            op_2_subn = ~op_2.sig[-1]

            # exponent before potential operand normalization
            pre_op_norm_exp = Signal(range(-2 * bias, bias + 1))
            sum_of_exp = op_1.exp + op_2.exp - 2 * bias
            # Because exp = 0 and exp = 1 represent the same exponent emin,
            # to properly calcuate pre_op_norm_exp we have to adjust those exponents
            # in case they are 0 and represent subnormal number
            subn_correction = op_1_subn + op_2_subn
            m.d.av_comb += pre_op_norm_exp.eq(sum_of_exp + subn_correction)

            # One of the ways to deal with subnormal values is to normalise them,
            # record additional shifts in exponent and adjust for this during normalization

            op_1_norm_shift = Signal(range(0, self.fpu_params.sig_width + 1))
            op_2_norm_shift = Signal(range(0, self.fpu_params.sig_width + 1))
            m.d.av_comb += op_1_norm_shift.eq(count_leading_zeros(op_1.sig))
            m.d.av_comb += op_2_norm_shift.eq(count_leading_zeros(op_2.sig))

            post_op_norm_exp = Signal(range(-2 * bias - 2 * self.fpu_params.sig_width, bias + 1))

            norm_op_1_sig = Signal(self.fpu_params.sig_width)
            norm_op_2_sig = Signal(self.fpu_params.sig_width)

            m.d.av_comb += norm_op_1_sig.eq(op_1.sig << op_1_norm_shift)
            m.d.av_comb += norm_op_2_sig.eq(op_2.sig << op_2_norm_shift)
            # TODO change names of some variables, they are awful
            # Use normalize to indicate that they come from this part?
            shifted_bit = Signal()

            sig_product = Signal(2 * self.fpu_params.sig_width)
            m.d.av_comb += multiplier.i1.eq(norm_op_1_sig)
            m.d.av_comb += multiplier.i2.eq(norm_op_2_sig)
            #m.d.av_comb += sig_product.eq((norm_op_1_sig * norm_op_2_sig))
            m.d.av_comb += sig_product.eq(multiplier.r)

            # First step of normalization
            # if sig is between [1,2) leave it alone
            # if sig is between [2,4) shift right by one
            sig_shifted_product = Signal((2 * self.fpu_params.sig_width) - 1)
            m.d.av_comb += sig_shifted_product.eq(sig_product)
            with m.If(sig_product[-1]):
                m.d.av_comb += sig_shifted_product.eq(sig_product >> 1)
                m.d.av_comb += shifted_bit.eq(sig_product[0])

            m.d.av_comb += post_op_norm_exp.eq(pre_op_norm_exp - (op_1_norm_shift + op_2_norm_shift) + sig_product[-1])
            sticky_bit = Signal()
            round_bit = Signal()
            final_exp = Signal(self.fpu_params.exp_width)
            final_sig = Signal(self.fpu_params.sig_width + 1)
            normalised_sig = Signal(self.fpu_params.sig_width + 1)
            #TODO comment about shift
            m.d.av_comb += normalised_sig.eq(sig_shifted_product >> (self.fpu_params.sig_width - 2))

            # TODO move RS bits computation outside if/else
            with m.If(post_op_norm_exp >= min_real_exp):
                m.d.av_comb += final_exp.eq(post_op_norm_exp + bias)
                m.d.av_comb += final_sig.eq(normalised_sig)
                shifted_bits = sig_shifted_product.bit_select(0, self.fpu_params.sig_width - 2).any()
                m.d.av_comb += sticky_bit.eq(shifted_bits | shifted_bit)
                with m.If(final_sig[-1] == 0):
                    # TODO find example that would result in this case being true
                    # highest possible normal value and subnormal ?
                    m.d.av_comb += final_exp.eq(0)
            with m.Elif(post_op_norm_exp < min_real_exp):
                # In this case value always will be subnormal
                m.d.av_comb += final_exp.eq(0)
                shift_needed = Signal(unsigned(self.fpu_params.exp_width))
                m.d.av_comb += shift_needed.eq(min_real_exp - post_op_norm_exp)
                m.d.av_comb += final_sig.eq(normalised_sig >> shift_needed)
                any_shifted_out = Signal()
                with m.If(shift_needed > (self.fpu_params.sig_width)):
                    m.d.av_comb += any_shifted_out.eq(sig_shifted_product.any())
                with m.Else():
                    # product has (2*p) - 1 bits, p ms bits represent the fp number
                    # p+1 bit is round bit and p - 2 ls bits for initial sticky bit
                    # For sticky bit we have to catch those p - 2 ls bits and shift_needed bits
                    # from p + 1 ms bits
                    padding = Signal().replicate(self.fpu_params.sig_width)
                    shifted_out = Cat(padding, sig_shifted_product).bit_select(
                        shift_needed, 2 * self.fpu_params.sig_width - 2
                    )
                    m.d.av_comb += any_shifted_out.eq(shifted_out.any())
                m.d.av_comb += sticky_bit.eq(any_shifted_out | shifted_bit)
            m.d.av_comb += round_bit.eq(final_sig[0])
            resp = rounding_module.rounding_request(
                m,
                sign=final_sign,
                sig=final_sig >> 1,
                exp=final_exp,
                round_bit=round_bit,
                sticky_bit=sticky_bit,
                rounding_mode=rounding_mode,
            )
            m.d.av_comb += rounding_response.eq(resp)

            is_inf = Signal()
            m.d.av_comb += is_inf.eq(op_1.is_inf | op_2.is_inf)
            bad_inf = Signal()
            m.d.av_comb += bad_inf.eq((op_1.is_inf & op_2.is_zero) | (op_2.is_inf & op_1.is_zero))
            is_zero = Signal()
            m.d.av_comb += is_zero.eq(op_1.is_zero | op_2.is_zero)
            is_nan = Signal()
            m.d.av_comb += is_nan.eq(op_1.is_nan | op_2.is_nan | bad_inf)

            exc_sig = Signal(self.fpu_params.sig_width)
            exc_exp = Signal(self.fpu_params.exp_width)
            exc_sign = Signal()
            inexact = Signal()
            invalid_operation = Signal()
            #TODO DUPLICATE CODE HERE AND BELOW
            m.d.av_comb += exc_sig.eq(rounding_response["sig"])
            m.d.av_comb += exc_exp.eq(rounding_response["exp"])
            with m.If(is_nan | is_inf | is_zero):
                m.d.av_comb += inexact.eq(0)
                with m.If(is_nan):
                    is_any_snan = ((~op_1.sig[-2]) & op_1.is_nan) | ((~op_2.sig[-2]) & op_2.is_nan)
                    with m.If(is_any_snan | bad_inf):
                        m.d.av_comb += invalid_operation.eq(1)
                        m.d.av_comb += exc_sign.eq(0)
                        m.d.av_comb += exc_exp.eq(self.common_values.max_exp)
                        m.d.av_comb += exc_sig.eq(self.common_values.canonical_nan_sig)
                with m.Elif(is_inf & ~(bad_inf)):
                    m.d.av_comb += exc_sign.eq(Mux(op_1.is_inf, op_1.sign, op_2.sign))
                    m.d.av_comb += (exc_exp.eq(Mux(op_1.is_inf, op_1.exp, op_2.exp)),)
                    m.d.av_comb += (exc_sig.eq(Mux(op_1.is_inf, op_1.sig, op_2.sig)),)
                with m.Elif(is_zero):
                    m.d.av_comb += exc_sign.eq(final_sign)
                    m.d.av_comb += exc_exp.eq(0)
                    m.d.av_comb += exc_sig.eq(0)
            with m.Else():
                m.d.av_comb += exc_sign.eq(final_sign)
                m.d.av_comb += exc_exp.eq(rounding_response["exp"])
                m.d.av_comb += inexact.eq(rounding_response["inexact"])
                with m.If(rounding_response["exp"] == self.common_values.max_exp):
                    m.d.av_comb += exc_sig.eq(2 ** (self.fpu_params.sig_width - 1))
                with m.Else():
                    m.d.av_comb += exc_sig.eq(rounding_response["sig"])

            resp = exception_module.error_checking_request(
                m,
                sign=exc_sign,
                sig=exc_sig,
                exp=exc_exp,
                rounding_mode=rounding_mode,
                inexact=inexact,
                invalid_operation=invalid_operation,
                division_by_zero=0,
                input_inf=is_inf,
            )
            m.d.av_comb += exception_response.eq(resp)

            return exception_response

        return m
