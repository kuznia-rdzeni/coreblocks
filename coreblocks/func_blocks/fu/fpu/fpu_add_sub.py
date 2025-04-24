from amaranth import *
from amaranth.lib import data
from transactron import TModule, Method, def_method
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


class FPUAddSubModule(Elaboratable):
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

        def gen_float(fpu_params: FPUParams):
            return Signal(
                data.StructLayout(
                    {
                        "sign": 1,
                        "sig": fpu_params.sig_width,
                        "exp": fpu_params.exp_width,
                    }
                )
            )

        def gen_ext_float(fpu_params: FPUParams):
            return Signal(
                data.StructLayout(
                    {
                        "sign": 1,
                        "sig": fpu_params.sig_width + 2,
                        "exp": fpu_params.exp_width,
                    }
                )
            )

        def assign_values(lhs, exp, sig, sign):
            m.d.av_comb += lhs.exp.eq(exp)
            m.d.av_comb += lhs.sig.eq(sig)
            m.d.av_comb += lhs.sign.eq(sign)

        m.submodules.close_path_module = close_path_module = ClosePathModule(fpu_params=self.fpu_params)
        m.submodules.far_path_module = far_path_module = FarPathModule(fpu_params=self.fpu_params)
        m.submodules.exception_module = exception_module = FPUErrorModule(fpu_params=self.fpu_params)

        max_exp = (2 ** (self.fpu_params.exp_width)) - 1

        final_sign = Signal(1)
        exp_diff = Signal(range(-max_exp, max_exp))
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
            op_2_true_sign = operation ^ op_2.sign

            m.d.av_comb += exp_diff.eq(op_1.exp - op_2.exp)

            pre_shift_op1 = gen_ext_float(self.fpu_params)
            pre_shift_op2 = gen_ext_float(self.fpu_params)

            with m.If(exp_diff == 0):
                sig_diff = op_1.sig - op_2.sig
                with m.If(sig_diff == 0):
                    assign_values(pre_shift_op1, op_1.exp, op_1.sig << 2, op_1.sign)
                    assign_values(pre_shift_op2, op_2.exp, op_2.sig << 2, op_2_true_sign)
                with m.Elif(sig_diff < 0):
                    assign_values(pre_shift_op1, op_2.exp, op_2.sig << 2, op_2_true_sign)
                    assign_values(pre_shift_op2, op_1.exp, op_1.sig << 2, op_1.sign)
                with m.Elif(sig_diff > 0):
                    assign_values(pre_shift_op1, op_1.exp, op_1.sig << 2, op_1.sign)
                    assign_values(pre_shift_op2, op_2.exp, op_2.sig << 2, op_2_true_sign)
            with m.Elif(exp_diff < 0):
                assign_values(pre_shift_op1, op_2.exp, op_2.sig << 2, op_2_true_sign)
                assign_values(pre_shift_op2, op_1.exp, op_1.sig << 2, op_1.sign)
            with m.Elif(exp_diff > 0):
                assign_values(pre_shift_op1, op_1.exp, op_1.sig << 2, op_1.sign)
                assign_values(pre_shift_op2, op_2.exp, op_2.sig << 2, op_2_true_sign)

            # m.d.av_comb += Print("exp_diff: ",exp_diff, " exp1: ", op_1.exp, " exp2: ", op_2.exp)
            # m.d.av_comb += Print(true_operation)
            sign_xor = pre_shift_op1.sign ^ pre_shift_op2.sign

            with m.If(~sign_xor):
                m.d.av_comb += final_sign.eq(pre_shift_op1.sign)
                m.d.av_comb += true_operation.eq(0)
            with m.Else():
                m.d.av_comb += final_sign.eq(pre_shift_op1.sign)
                m.d.av_comb += true_operation.eq(1)

            is_one_subnormal = (pre_shift_op1.exp > 0) & (pre_shift_op2.exp == 0)
            m.d.av_comb += norm_shift_amount.eq(pre_shift_op1.exp - pre_shift_op2.exp - is_one_subnormal)

            # m.d.av_comb += Print("nsa: ",norm_shift_amount)

            path_op1 = gen_float(self.fpu_params)
            path_op2_ext = gen_ext_float(self.fpu_params)
            path_op2 = gen_float(self.fpu_params)

            m.d.av_comb += path_op1.sig.eq(pre_shift_op1.sig)
            with m.If(norm_shift_amount > (self.fpu_params.sig_width + 2)):
                m.d.av_comb += sticky_bit.eq(pre_shift_op2.sig.any())
                m.d.av_comb += path_op2_ext.sig.eq(0)
            with m.Else():
                l_shift = Signal(range(0, self.fpu_params.sig_width + 2))
                sticky_bit_mask = Signal(self.fpu_params.sig_width + 2)
                m.d.av_comb += l_shift.eq((self.fpu_params.sig_width + 2) - norm_shift_amount)
                m.d.av_comb += sticky_bit_mask.eq(pre_shift_op2.sig << l_shift)
                m.d.av_comb += sticky_bit.eq(sticky_bit_mask.any())
                m.d.av_comb += path_op2_ext.sig.eq(pre_shift_op2.sig >> norm_shift_amount)

            guard_bit = path_op2_ext.sig[1]
            round_bit = path_op2_ext.sig[0]

            assign_values(path_op1, pre_shift_op1.exp, pre_shift_op1.sig >> 2, pre_shift_op1.sign)
            with m.If(true_operation):
                assign_values(
                    path_op2, (pre_shift_op2.exp + norm_shift_amount), ~(path_op2_ext.sig >> 2), pre_shift_op2.sign
                )
            with m.Else():
                assign_values(
                    path_op2, (pre_shift_op2.exp + norm_shift_amount), path_op2_ext.sig >> 2, pre_shift_op2.sign
                )

            # m.d.av_comb += Print(Format("op1_exp: {:08b}",path_op1.exp))
            # m.d.av_comb += Print(Format(" op1_sig: {:024b}", path_op1.sig))
            # m.d.av_comb += Print(Format(" op2_sig: {:024b}", path_op2.sig))
            close_path = (norm_shift_amount <= 1) & true_operation
            # m.d.av_comb += Print(guard_bit)
            resp = Mux(
                close_path,
                close_path_module.close_path_request(
                    m,
                    r_sign=final_sign,
                    sig_a=path_op1.sig,
                    sig_b=path_op2.sig,
                    exp=path_op1.exp,
                    rounding_mode=rounding_mode,
                    guard_bit=guard_bit,
                ),
                far_path_module.far_path_request(
                    m,
                    r_sign=final_sign,
                    sig_a=path_op1.sig,
                    sig_b=path_op2.sig,
                    exp=path_op1.exp,
                    sub_op=true_operation,
                    rounding_mode=rounding_mode,
                    guard_bit=guard_bit,
                    round_bit=round_bit,
                    sticky_bit=sticky_bit,
                ),
            )
            m.d.av_comb += path_response.eq(resp)
            # m.d.av_comb += Print("out_exp: ",path_response["out_exp"], " out_sig:", path_response["out_sig"])

            eq_signs = path_op2.sign == path_op1.sign
            is_inf = op_1.is_inf | op_2.is_inf
            wrong_inf = (op_1.is_inf & op_2.is_inf) & ~(eq_signs)
            is_nan = (op_1.is_nan | op_2.is_nan) | wrong_inf
            output_zero = (path_response["out_exp"] == 0) & (path_response["out_sig"] == 0)
            output_exact = ~(path_response["output_round"] | path_response["output_sticky"])
            both_op_zero = op_1.is_zero & op_2.is_zero
            is_zero = both_op_zero | (output_exact & output_zero)
            normal_case = ~(is_nan | is_inf | is_zero)
            exception_op = gen_float(self.fpu_params)

            # m.d.av_comb += Print(normal_case)

            with m.If(~normal_case):
                m.d.av_comb += exception_round_bit.eq(0)
                m.d.av_comb += exception_sticky_bit.eq(0)

            with m.If(is_inf & ~(wrong_inf)):
                m.d.av_comb += exception_op.sign.eq(op_1.sign)
                m.d.av_comb += exception_op.exp.eq(op_1.exp)
                m.d.av_comb += exception_op.sig.eq(op_1.sig)
            with m.Elif(is_nan):
                is_any_snan = (~op_1.sig[-2]) | (~op_2.sig[-2])
                with m.If(is_any_snan | wrong_inf):
                    m.d.av_comb += invalid_operation.eq(1)
                m.d.av_comb += exception_op.sign.eq(0)
                m.d.av_comb += exception_op.exp.eq(max_exp)
                m.d.av_comb += exception_op.sig.eq(self.common_values.canonical_nan_sig)
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
                m.d.av_comb += exception_op.sig.eq(path_response["out_sig"])
                m.d.av_comb += exception_round_bit.eq(path_response["output_round"])
                m.d.av_comb += exception_sticky_bit.eq(path_response["output_sticky"])

            # m.d.av_comb += Print(Format(" op1e_sig: {:024b}", exception_op.sig))
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
