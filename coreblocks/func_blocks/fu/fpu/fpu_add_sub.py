from amaranth import *
from transactron import TModule, Method, def_method
from transactron.utils import assign
from transactron.utils.transactron_helpers import from_method_layout
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    create_data_input_layout,
    create_output_layout,
    create_raw_float_layout,
    FPUCommonValues,
)
from coreblocks.func_blocks.fu.fpu.far_path import FarPathModule
from coreblocks.func_blocks.fu.fpu.close_path import ClosePathModule
from coreblocks.func_blocks.fu.fpu.fpu_error_module import FPUErrorModule


class FPUAddSubMethodLayout:
    """FPU addition/subtraction top module method layout

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.add_sub_in_layout = [
            ("op_1", create_data_input_layout(fpu_params)),
            ("op_2", create_data_input_layout(fpu_params)),
            ("rounding_mode", RoundingModes),
            ("operation", 1),
        ]
        """
        | Input layout for addition/subtraction
        | op_1 - layout containing data of the first operand
        | op_2 - layout containing data of the second operand
        | rounding_mode - selected rounding mode
        | op - selected operation; 1 - subtraction, 0 - addition
        | op_1 and op_2 are created using
          :meth:`create_data_input_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_data_input_layout>`
        """
        self.add_sub_out_layout = create_output_layout(fpu_params)
        """
        Output layout for addition/subtraction. Created using
        :meth:`create_output_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_output_layout>`
        """
        self.raw_float_layout = create_raw_float_layout(fpu_params)
        """
        Output layout for raw float. Created using
        :meth:`create_raw_float_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_raw_float_layout>`
        """
        ext_paramas = FPUParams(sig_width=fpu_params.sig_width + 2, exp_width=fpu_params.exp_width)
        self.ext_float_layout = create_raw_float_layout(ext_paramas)
        """
        Output layout for raw float with significand larger by two bits from selected format.
        Created using
        :meth:`create_raw_float_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_raw_float_layout>`
        """


class FPUAddSubModule(Elaboratable):
    """
    | FPU addition/subtraction top module
    | This module implements addition and subtraction using
      two path approach with rounding prediction.
    | The module can be divided into two segments:
    | 1. Receiving data and preparing it for one of the two path submodules
      by calculating effective operation, swapping operands and aligning exponents.
    | 2. Receiving data from one of the path submodules and preparing it for error checking
      module by checking for various conditions
    | For more info about close path and far path check
      :meth:`close path module <coreblocks.func_blocks.fu.fpu.close_path.ClosePathModule>`
       and
      :meth:`far path module <coreblocks.func_blocks.fu.fpu.far_path.FarPathModule>`

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    add_sub_request: Method
        Transactional method for initiating addition or subtraction.
        Takes
        :meth:`add_sub_in_layout <coreblocks.func_blocks.fu.fpu.fpu_add_sub.FPUAddSubMethodLayout.add_sub_in_layout>`
        as argument.
        Returns result as
        :meth:`add_sub_out_layout <coreblocks.func_blocks.fu.fpu.fpu_add_sub.FPUAddSubMethodLayout.add_sub_out_layout>`.
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.fpu_params = fpu_params
        self.method_layouts = FPUAddSubMethodLayout(fpu_params=self.fpu_params)
        self.common_values = FPUCommonValues(self.fpu_params)
        self.add_sub_request = Method(
            i=self.method_layouts.add_sub_in_layout,
            o=self.method_layouts.add_sub_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        def assign_values(lhs, exp, sig, sign):
            m.d.av_comb += assign(lhs, {"sign": sign, "exp": exp, "sig": sig})

        m.submodules.close_path_module = close_path_module = ClosePathModule(fpu_params=self.fpu_params)
        m.submodules.far_path_module = far_path_module = FarPathModule(fpu_params=self.fpu_params)
        m.submodules.exception_module = exception_module = FPUErrorModule(fpu_params=self.fpu_params)

        max_exp = (2 ** (self.fpu_params.exp_width)) - 1

        final_sign = Signal(1)
        exp_diff = Signal(range(-max_exp, max_exp + 1))
        norm_shift_amount = Signal(range(max_exp))
        sticky_bit = Signal(1)
        true_operation = Signal(1)
        exception_round_bit = Signal(1)
        exception_sticky_bit = Signal(1)
        invalid_operation = Signal(1)

        path_response = Signal(from_method_layout(far_path_module.method_layouts.far_path_out_layout))
        exception_response = Signal(from_method_layout(exception_module.method_layouts.error_out_layout))

        @def_method(m, self.add_sub_request)
        def _(op_1, op_2, rounding_mode, operation):
            op_2_true_sign = Signal()
            m.d.av_comb += op_2_true_sign.eq(operation ^ op_2.sign)

            m.d.av_comb += exp_diff.eq(op_1.exp - op_2.exp)

            # Swapping operands to ensure that pre_shift_op1 <= pre_shift_op2
            pre_shift_op1 = Signal(from_method_layout(self.method_layouts.ext_float_layout))
            pre_shift_op2 = Signal(from_method_layout(self.method_layouts.ext_float_layout))
            assign_values(pre_shift_op1, op_1.exp, op_1.sig << 2, op_1.sign)
            assign_values(pre_shift_op2, op_2.exp, op_2.sig << 2, op_2_true_sign)

            with m.If(exp_diff == 0):
                sig_diff = Signal(range(-self.common_values.max_sig, self.common_values.max_sig + 1))
                m.d.av_comb += sig_diff.eq(op_1.sig - op_2.sig)
                with m.If(sig_diff < 0):
                    assign_values(pre_shift_op1, op_2.exp, op_2.sig << 2, op_2_true_sign)
                    assign_values(pre_shift_op2, op_1.exp, op_1.sig << 2, op_1.sign)
            with m.Elif(exp_diff < 0):
                assign_values(pre_shift_op1, op_2.exp, op_2.sig << 2, op_2_true_sign)
                assign_values(pre_shift_op2, op_1.exp, op_1.sig << 2, op_1.sign)

            # Calculating true operation based on signs of swapped operands
            sign_xor = op_1.sign ^ op_2_true_sign

            m.d.av_comb += final_sign.eq(pre_shift_op1.sign)

            with m.If(~sign_xor):
                m.d.av_comb += true_operation.eq(0)
            with m.Else():
                m.d.av_comb += true_operation.eq(1)

            is_one_subnormal = (pre_shift_op1.exp > 0) & (pre_shift_op2.exp == 0)
            m.d.av_comb += norm_shift_amount.eq(pre_shift_op1.exp - pre_shift_op2.exp - is_one_subnormal)

            # Aligning exponents and calculating GRB bits
            path_op1 = Signal(from_method_layout(self.method_layouts.raw_float_layout))
            far_path_op2_ext = Signal(from_method_layout(self.method_layouts.ext_float_layout))
            far_path_op2 = Signal(from_method_layout(self.method_layouts.raw_float_layout))
            close_path_op2 = Signal(from_method_layout(self.method_layouts.raw_float_layout))

            m.d.av_comb += path_op1.sig.eq(pre_shift_op1.sig)
            with m.If(norm_shift_amount > (self.fpu_params.sig_width + 2)):
                m.d.av_comb += sticky_bit.eq(pre_shift_op2.sig.any())
                m.d.av_comb += far_path_op2_ext.sig.eq(0)
            with m.Else():
                sticky_bit_mask = Cat(Signal().replicate(self.fpu_params.sig_width), pre_shift_op2.sig).bit_select(
                    norm_shift_amount, self.fpu_params.sig_width
                )
                m.d.av_comb += sticky_bit.eq(sticky_bit_mask.any())
                m.d.av_comb += far_path_op2_ext.sig.eq(pre_shift_op2.sig >> norm_shift_amount)

            close_path_guard_bit = Signal()

            with m.If(norm_shift_amount[0] == 0):
                m.d.av_comb += close_path_op2.sig.eq(~(pre_shift_op2.sig >> 2))
                m.d.av_comb += close_path_guard_bit.eq(0)
            with m.Else():
                m.d.av_comb += close_path_op2.sig.eq(~(pre_shift_op2.sig >> 3))
                m.d.av_comb += close_path_guard_bit.eq(pre_shift_op2.sig[2])

            guard_bit = far_path_op2_ext.sig[1]
            round_bit = far_path_op2_ext.sig[0]

            # Assigning operands for close path and far path
            assign_values(path_op1, pre_shift_op1.exp, pre_shift_op1.sig >> 2, pre_shift_op1.sign)
            assign_values(
                far_path_op2,
                (pre_shift_op2.exp + norm_shift_amount),
                Mux(true_operation, ~(far_path_op2_ext.sig >> 2), far_path_op2_ext.sig >> 2),
                pre_shift_op2.sign,
            )

            close_path = (norm_shift_amount <= 1) & true_operation
            resp = Mux(
                close_path,
                close_path_module.close_path_request(
                    m,
                    r_sign=final_sign,
                    sig_a=path_op1.sig,
                    sig_b=close_path_op2.sig,
                    exp=path_op1.exp,
                    rounding_mode=rounding_mode,
                    guard_bit=close_path_guard_bit,
                ),
                far_path_module.far_path_request(
                    m,
                    r_sign=final_sign,
                    sig_a=path_op1.sig,
                    sig_b=far_path_op2.sig,
                    exp=path_op1.exp,
                    sub_op=true_operation,
                    rounding_mode=rounding_mode,
                    guard_bit=guard_bit,
                    round_bit=round_bit,
                    sticky_bit=sticky_bit,
                ),
            )

            # Preparing data for error checking module
            m.d.av_comb += path_response.eq(resp)
            eq_signs = pre_shift_op2.sign == path_op1.sign
            is_inf = op_1.is_inf | op_2.is_inf
            wrong_inf = (op_1.is_inf & op_2.is_inf) & ~(eq_signs)
            is_nan = (op_1.is_nan | op_2.is_nan) | wrong_inf
            output_zero = (path_response["out_exp"] == 0) & (path_response["out_sig"] == 0)
            output_exact = ~(path_response["output_round"] | path_response["output_sticky"])
            both_op_zero = op_1.is_zero & op_2.is_zero
            is_zero = Signal()
            m.d.av_comb += is_zero.eq(both_op_zero | (output_exact & output_zero))
            normal_case = ~(is_nan | is_inf | is_zero)
            exception_op = Signal(from_method_layout(self.method_layouts.raw_float_layout))

            with m.If(~normal_case):
                m.d.av_comb += exception_round_bit.eq(0)
                m.d.av_comb += exception_sticky_bit.eq(0)
            with m.If(is_nan):
                is_any_snan = ((~op_1.sig[-2]) & op_1.is_nan) | ((~op_2.sig[-2]) & op_2.is_nan)
                with m.If(is_any_snan | wrong_inf):
                    m.d.av_comb += invalid_operation.eq(1)
                m.d.av_comb += exception_op.sign.eq(0)
                m.d.av_comb += exception_op.exp.eq(max_exp)
                m.d.av_comb += exception_op.sig.eq(self.common_values.canonical_nan_sig)
            with m.Elif(is_inf & ~(wrong_inf)):
                assign_values(
                    exception_op,
                    Mux(op_1.is_inf, op_1.exp, op_2.exp),
                    Mux(op_1.is_inf, op_1.sig, op_2.sig),
                    Mux(op_1.is_inf, op_1.sign, pre_shift_op2.sign),
                )
            with m.Elif(is_zero):
                with m.If(eq_signs):
                    m.d.av_comb += exception_op.sign.eq(op_1.sign)
                with m.Else():
                    m.d.av_comb += exception_op.sign.eq(rounding_mode == RoundingModes.ROUND_DOWN)
                m.d.av_comb += exception_op.exp.eq(0)
                m.d.av_comb += exception_op.sig.eq(0)
            with m.Elif(normal_case):
                m.d.av_comb += exception_op.sign.eq(final_sign)
                m.d.av_comb += exception_op.exp.eq(path_response["out_exp"])
                m.d.av_comb += exception_round_bit.eq(path_response["output_round"])
                m.d.av_comb += exception_sticky_bit.eq(path_response["output_sticky"])
                with m.If(path_response["out_exp"] == max_exp):
                    m.d.av_comb += exception_op.sig.eq(2 ** (self.fpu_params.sig_width - 1))
                with m.Else():
                    m.d.av_comb += exception_op.sig.eq(path_response["out_sig"])

            inexact = exception_sticky_bit | exception_round_bit
            resp = exception_module.error_checking_request(
                m,
                sign=exception_op.sign,
                sig=exception_op.sig,
                exp=exception_op.exp,
                rounding_mode=rounding_mode,
                inexact=inexact,
                invalid_operation=invalid_operation,
                division_by_zero=0,
                input_inf=is_inf,
            )
            m.d.av_comb += exception_response.eq(resp)

            return exception_response

        return m
