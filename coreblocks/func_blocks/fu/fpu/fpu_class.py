from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    FPUParams,
    FPUClasses,
    create_data_input_layout,
    Errors,
)


class FPUClassMethodLayout:
    """FPU classification module method layout

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        self.class_in_layout = [
            ("op", create_data_input_layout(fpu_params)),
        ]
        """
        | Input layout for classification
        | op - layout containing data of the only operand
        """
        self.class_out_layout = [
            ("result", FPUClasses),
            ("errors", Errors),
        ]
        """
        | Output layout for classification
        | result - Class of operand
        | errors - Exceptions, in case of classification it is always 0 (empty mask)
        """


class FPUClassModule(Elaboratable):
    """Classification module
    Module responsible for performing classification.

    Parameters
    ----------
    fpu_params: FPUParams
        FPU format parameters

    Attributes
    ----------
    class_request: Method
        Transactional method for initiating classification.
        Takes 'class_in_layout' as argument
        Returns result as 'class_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.class_params = fpu_params
        self.method_layouts = FPUClassMethodLayout(fpu_params=self.class_params)
        self.class_request = Method(
            i=self.method_layouts.class_in_layout,
            o=self.method_layouts.class_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.class_request)
        def _(op):
            normal_case = Signal()
            neg_sign = Signal()
            pos_sign = Signal()
            op_norm = Signal()
            op_sub = Signal()
            op_sig_nan = Signal()
            m.d.av_comb += neg_sign.eq(op.sign)
            m.d.av_comb += pos_sign.eq(~op.sign)
            m.d.av_comb += normal_case.eq((~op.is_inf) & (~op.is_zero) & (~op.is_nan))
            m.d.av_comb += op_norm.eq(normal_case & (op.exp > 0))
            m.d.av_comb += op_sub.eq(normal_case & (op.exp == 0))
            m.d.av_comb += op_sig_nan.eq(op.is_nan & (~op.sig[-2]))

            result = Signal(FPUClasses)

            with m.If(op.is_nan):
                with m.If(~op_sig_nan):
                    m.d.av_comb += result.eq(FPUClasses.QUIET_NAN)
                with m.Elif(op_sig_nan):
                    m.d.av_comb += result.eq(FPUClasses.SIG_NAN)
            with m.Elif(neg_sign):
                with m.If(op.is_inf):
                    m.d.av_comb += result.eq(FPUClasses.NEG_INF)
                with m.Elif(op_norm):
                    m.d.av_comb += result.eq(FPUClasses.NEG_NORM)
                with m.Elif(op_sub):
                    m.d.av_comb += result.eq(FPUClasses.NEG_SUB)
                with m.Elif(op.is_zero):
                    m.d.av_comb += result.eq(FPUClasses.NEG_ZERO)
            with m.Elif(pos_sign):
                with m.If(op.is_inf):
                    m.d.av_comb += result.eq(FPUClasses.POS_INF)
                with m.Elif(op_norm):
                    m.d.av_comb += result.eq(FPUClasses.POS_NORM)
                with m.Elif(op_sub):
                    m.d.av_comb += result.eq(FPUClasses.POS_SUB)
                with m.Elif(op.is_zero):
                    m.d.av_comb += result.eq(FPUClasses.POS_ZERO)

            return {
                "result": result,
                "errors": 0,
            }

        return m
