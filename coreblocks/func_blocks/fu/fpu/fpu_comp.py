from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    FPUParams,
    ComparisionTypes,
    create_data_input_layout,
    Errors,
)


class FPUCompMethodLayout:
    """FPU comparision module method layout

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.comp_in_layout = [
            ("op_1", create_data_input_layout(fpu_params)),
            ("op_2", create_data_input_layout(fpu_params)),
            ("operation", ComparisionTypes),
        ]
        """
        | Input layout for comparision
        | op_1 - layout containing data of the first operand
        | op_2 - layout containing data of the second operand
        | operation - selected operation, values come from
          :class:`ComparisionTypes <coreblocks.func_blocks.fu.fpu.fpu_common.ComparisionTypes>`
        """
        self.comp_out_layout = [
            ("result", 1),
            ("errors", Errors),
        ]
        """
        | Output layout for comparision
        | result - 1 if true or 0 otherwise
        | errors - Exceptions, in this case the only possible exception is invalid operation
        """


class FPUCompModule(Elaboratable):
    """Comparision module
    Module responsible for performing LT, EQ and LE  operations.

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    comp_request: Method
        Transactional method for initiating comparision.
        Takes 'comp_in_layout' as argument
        Returns result as 'comp_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.comp_params = fpu_params
        self.method_layouts = FPUCompMethodLayout(fpu_params=self.comp_params)
        self.comp_request = Method(
            i=self.method_layouts.comp_in_layout,
            o=self.method_layouts.comp_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.comp_request)
        def _(op_1, op_2, operation):
            signaling_op = Signal()
            m.d.av_comb += signaling_op.eq((operation == ComparisionTypes.LE) | (operation == ComparisionTypes.LT))

            ordered = Signal()
            m.d.av_comb += ordered.eq(~(op_1.is_nan | op_2.is_nan))

            op_1_sig_nan = op_1.is_nan & (~op_1.sig[-2])
            op_2_sig_nan = op_2.is_nan & (~op_2.sig[-2])
            any_nan_signaling = Signal()
            m.d.av_comb += any_nan_signaling.eq(op_1_sig_nan | op_2_sig_nan)

            both_inf = Signal()
            m.d.av_comb += both_inf.eq(op_1.is_inf & op_2.is_inf)

            both_zero = Signal()
            m.d.av_comb += both_zero.eq(op_1.is_zero & op_2.is_zero)

            same_sign = Signal()
            m.d.av_comb += same_sign.eq(op_1.sign == op_2.sign)

            eq_exp = Signal()
            m.d.av_comb += eq_exp.eq(op_1.exp == op_2.exp)
            lt_exp = op_1.exp < op_2.exp
            lt_sig = op_1.sig < op_2.sig
            eq_sig = op_1.sig == op_2.sig

            eq_mag = Signal()
            lt_mag = Signal()
            m.d.av_comb += eq_mag.eq(eq_exp & eq_sig)
            m.d.av_comb += lt_mag.eq(lt_exp | (eq_exp & lt_sig))

            lt = Signal()
            mag_gt = (~eq_mag) & (~lt_mag)
            lt_by_sign = op_1.sign & (~op_2.sign)
            lt_sign_neg = op_1.sign & mag_gt
            lt_sign_pos = (~op_2.sign) & lt_mag
            m.d.av_comb += lt.eq((~both_zero) & (lt_by_sign | lt_sign_neg | lt_sign_pos))

            equal = Signal()
            m.d.av_comb += equal.eq(both_zero | (same_sign & eq_mag))

            result = Signal()

            with m.Switch(operation):
                with m.Case(ComparisionTypes.EQ):
                    m.d.av_comb += result.eq(ordered & equal)
                with m.Case(ComparisionTypes.LT):
                    m.d.av_comb += result.eq(ordered & lt)
                with m.Case(ComparisionTypes.LE):
                    m.d.av_comb += result.eq(ordered & (equal | lt))

            invalid = Signal(Errors)
            with m.If(any_nan_signaling | (signaling_op & (~ordered))):
                m.d.av_comb += invalid.eq(Errors.INVALID_OPERATION)
            return {
                "result": result,
                "errors": invalid,
            }

        return m
