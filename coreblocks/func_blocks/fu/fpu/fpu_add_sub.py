from amaranth import *
from transactron import TModule, Method, def_method, Transaction
from transactron.utils.transactron_helpers import from_method_layout
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    create_data_layout,
    create_output_layout,
    FPUCommonValues,
)
from coreblocks.func_blocks.fu.fpu.far_path import FarPathModule
from coreblocks.func_blocks.fu.fpu.close_path import ClosePathModule
from coreblocks.func_blocks.fu.fpu.fpu_error_module import FPUErrorModule


class FPUAddSubMethodLayout:
    def __init__(self, *, fpu_params: FPUParams):
        self.add_sub_in_layout = [
            ("op_1", create_data_layout(fpu_params)),
            ("op_2", create_data_layout(fpu_params)),
            ("rounding_mode", RoundingModes),
            ("operation", 1),
        ]
        self.add_sub_out_layout = create_output_layout(fpu_params)


class FPUAddSub:
    def __init__(self, *, fpu_params: FPUParams):
        self.fpu_params = fpu_params
        self.method_layouts = FPUAddSubMethodLayout(self.fpu_params)
        self.common_values = FPUCommonValues(self.fpu_params)
        self.add_sub_request = Method(
            i=self.method_layouts.add_sub_in_layout,
            o=self.method_layouts.add_sub_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.close_path_module = close_path_module = ClosePathModule(fpu_params=self.params)
        m.submodules.far_path_module = far_path_module = FarPathModule(fpu_params=self.params)
        m.submodules.exception_module = exception_module = FPUErrorModule(fpu_params=self.params)

        max_exp = 2 ^ (self.fpu_params.exp_width) - 1

        final_sign = Signal(1)

        op1_sig_ext = Signal(self.fpu_params.sig_width + 2)
        op2_sig_ext = Signal(self.fpu_params.sig_width + 2)
        op2_sig_final = Signal(self.fpu_params.sig_width + 2)
        true_op1_sig = Signal(self.fpu_params.sig_width)
        true_op2_sig = Signal(self.fpu_params.sig_width)
        true_op1_exp = Signal(self.fpu_params.exp_width)
        true_op2_exp = Signal(self.fpu_params.exp_width)
        true_op1_sign = Signal(1)
        true_op2_sign = Signal(1)
        exp_diff = Signal(range(-max_exp, max_exp))
        norm_shift_amount = Signal(range(max_exp))
        # numbers_eq = Signal(1)
        sticky_bit = Signal(1)
        true_operation = Signal(1)
        exception_round_bit = Signal(1)
        exception_sticky_bit = Signal(1)
        exception_sign = Signal(1)
        exception_sig = Signal(self.fpu_params.sig_width)
        exception_exp = Signal(self.fpu_params.exp_width)
        invalid_operation = Signal(1)

        path_response = Signal(from_method_layout(far_path.method_layouts.far_path_out_layout))
        exception_response = Signal(from_method_layout(exception_module.method_layouts.error_out_layout))

        @def_method(m, self.add_sub_request)
        def _(op_1, op_2, rounding_mode, operation):
            op_2_true_sign = operation ^ op_2.sign

            m.d.av_comb += exp_diff.eq(op_1.exp - op_2.exp)

            with m.If(exp_diff == 0):
                sig_diff = op_1.sig - op_2.sig
                with m.If(sig_diff == 0):
                    # m.d.av_comb += numbers_eq.eq(1)
                    m.d.av_comb += true_op1_exp.eq(op_1.exp)
                    m.d.av_comb += true_op2_exp.eq(op_2.exp)
                    m.d.av_comb += op1_sig_ext.eq(op_1.sig << 2)
                    m.d.av_comb += op2_sig_ext.eq(op_2.sig << 2)
                    m.d.av_comb += true_op1_sign.eq(op_1.sign)
                    m.d.av_comb += true_op2_sign.eq(op_2_true_sign)
                with m.Elif(sig_diff < 0):
                    m.d.av_comb += true_op1_exp.eq(op_2.exp)
                    m.d.av_comb += true_op2_exp.eq(op_1.exp)
                    m.d.av_comb += op1_sig_ext.eq(op_2.sig << 2)
                    m.d.av_comb += op2_sig_ext.eq(op_1.sig << 2)
                    m.d.av_comb += true_op1_sign.eq(op_2_true_sign)
                    m.d.av_comb += true_op2_sign.eq(op_1.sign)
                with m.Elif(sig_diff > 0):
                    m.d.av_comb += true_op1_exp.eq(op_1.exp)
                    m.d.av_comb += true_op2_exp.eq(op_2.exp)
                    m.d.av_comb += op1_sig_ext.eq(op_1.sig << 2)
                    m.d.av_comb += op2_sig_ext.eq(op_2.sig << 2)
                    m.d.av_comb += true_op1_sign.eq(op_1.sign)
                    m.d.av_comb += true_op2_sign.eq(op_2_true_sign)
            with m.Elif(exp_diff < 0):
                m.d.av_comb += true_op1_exp.eq(op_2.exp)
                m.d.av_comb += true_op2_exp.eq(op_1.exp)
                m.d.av_comb += op1_sig_ext.eq(op_2.sig << 2)
                m.d.av_comb += op2_sig_ext.eq(op_1.sig << 2)
                m.d.av_comb += true_op1_sign.eq(op_2_true_sign)
                m.d.av_comb += true_op2_sign.eq(op_1.sign)
            with m.Elif(exp_diff > 0):
                m.d.av_comb += true_op1_exp.eq(op_1.exp)
                m.d.av_comb += true_op2_exp.eq(op_2.exp)
                m.d.av_comb += op1_sig_ext.eq(op_1.sig << 2)
                m.d.av_comb += op2_sig_ext.eq(op_2.sig << 2)
                m.d.av_comb += true_op1_sign.eq(op_1.sign)
                m.d.av_comb += true_op2_sign.eq(op_2_true_sign)

            sign_xor = true_op1_sign ^ true_op2_sign
            with m.If(~sign_xor):
                m.d.av_comb += final_sign.eq(true_op1_sign)
                m.d.av_comb += true_operation.eq(0)
            with m.Else:
                m.d.av_comb += final_sign.eq(true_op1_sign)
                m.d.av_comb += true_operation.eq(true_op2_sign ^ true_op_1_sign)

            is_one_subnormal = (true_op1_exp > 0) & (true_op2_exp == 0)
            m.d.av_comb += norm_shift_amount.eq(true_op1_exp - true_op2_exp - is_one_subnormal)

            m.d.av_comb += true_op1_sig.eq(op1_sig_ext)
            with m.If(norm_shift_amount > (self.fpu_params.sig_width + 2)):
                m.d.av_comb += sticky_bit.eq(true_op2_sig.any())
                with m.If(true_operation):
                    m.d.av_comb += op2_sig_final.eq(~0)
                with m.Else():
                    m.d.av_comb += op2_sig_final.eq(0)
            with m.Else:
                m.d.av_comb += sticky_bit.eq(true_op2_sig[0:norm_shift_amount].any())
                with m.If(true_operation):
                    m.d.av_comb += op2_sig_final.eq(true_op2_sig >> norm_shift_amount)
                with m.Else():
                    m.d.av_comb += op2_sig_final.eq(~(true_op2_sig >> norm_shift_amount))

            guard_bit = op1_sig_final[1]
            round_bit = op1_sig_final[0]

            close_path = (norm_shift_amount > 1) & true_operation

            with Transaction().body(m):
                resp = Mux(
                    close_path,
                    close_path_module.close_path_request(
                        m,
                        r_sign=final_sign,
                        sig_a=op1_sig_final,
                        sig_b=op2_sig_final,
                        exp=true_op1_exp,
                        rounding_mode=rounding_mode,
                        guard_bit=guard_bit,
                        round_bit=round_bit,
                        sticky_bit=sticky_bit,
                    ),
                    far_path_module.far_path_request(
                        m,
                        r_sign=final_sign,
                        sig_a=op1_sig_final,
                        sig_b=op2_sig_final,
                        exp=true_op1_exp,
                        sub_op=true_operation,
                        rounding_mode=rounding_mode,
                        guard_bit=guard_bit,
                        round_bit=round_bit,
                        sticky_bit=sticky_bit,
                    ),
                )
                m.d.av_comb += path_response.eq(resp)

            is_inf = op_1.is_inf | op_2.is_inf
            is_nan = op_1.is_nan | op_2.is_nan
            is_zero = op_1.is_zero & op_2.is_zero
            normal_case = ~(is_nan | is_inf | is_zero)

            with m.If(~normal_case):
                m.d.av_comb += exception_round_bit.eq(0)
                m.d.av_comb += exception_sticky_bit.eq(0)

            with m.If(is_inf):
                with m.If(op_1.is_inf & op_2.is_inf):
                    m.d.av_comb += exception_sign.eq(0)
                    m.d.av_comb += exception_exp.eq(max_exp)
                    m.d.av_comb += exception_sig.eq(common_values.canonical_nan_sig)
                    m.d.av_comb += invalid_operation.eq(1)
                with m.Else():
                    m.d.av_comb += exception_sign.eq(final_sign)
                    m.d.av_comb += exception_exp.eq(op1_exp_final)
                    m.d.av_comb += exception_sig.eq(op1_sig_final)
            with m.Elif(is_nan):
                is_any_snan = (~op_1.sig[-2]) | (~op_2.sig[-2])
                with m.If(is_any_snan):
                    m.d.av_comb += invalid_operation.eq(1)
                m.d.av_comb += exception_sign.eq(0)
                m.d.av_comb += exception_exp.eq(max_exp)
                m.d.av_comb += exception_sig.eq(common_values.canonical_nan_sig)
            with m.Elif(is_zero):
                m.d.av_comb += exception_sign.eq(final_sign)
                m.d.av_comb += exception_exp.eq(0)
                m.d.av_comb += exception_sig.eq(0)
            with m.Elif(normal_case):
                m.d.av_comb += exception_sign.eq(final_sign)
                m.d.av_comb += exception_exp.eq(path_response["out_exp"])
                m.d.av_comb += exception_sig.eq(path_response["out_sig"])
                m.d.av_comb += exception_round_bit.eq(path_response["output_round"])
                with m.If(close_path):
                    m.d.av_comb += exception_sticky_bit.eq(0)
                with m.Else():
                    m.d.av_comb += exception_sticky_bit.eq(path_response["output_sticky"])

            inexact = exception_sticky_bit | exception_round_bit
            with Transaction().body(m):
                resp = exception_module.error_checking_request(
                    m,
                    sign=exception_sign,
                    sig=exception_sig,
                    exp=exception_exp,
                    rounding_mode=rounding_mode,
                    inexact=inexact,
                    invalid_operation=invalid_operation,
                    division_by_zero=0,
                    input_inf=is_inf,
                )
                m.d.av_comb += exception_response.eq(resp)

            return exception_response

        return m
