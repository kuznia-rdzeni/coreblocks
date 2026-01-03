from amaranth import *
from amaranth.lib import enum
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    FPUParams,
    create_data_input_layout,
    Errors,
)


class FPUClasses(enum.IntFlag):
    NEG_INF = enum.auto()
    NEG_NORM = enum.auto()
    NEG_SUB = enum.auto()
    NEG_ZERO = enum.auto()
    POS_ZERO = enum.auto()
    POS_SUB = enum.auto()
    POS_NORM = enum.auto()
    POS_INF = enum.auto()
    SIG_NAN = enum.auto()
    QUIET_NAN = enum.auto()


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
        | op_1 - layout containing data of the only operand
        """
        self.class_out_layout = [
            ("result", 10),
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
            common_case = Signal()
            neg_sign = Signal()
            pos_sign = Signal()
            op_norm = Signal()
            op_sub = Signal()
            op_sig_nan = Signal()
            m.d.av_comb += neg_sign.eq(op.sign)
            m.d.av_comb += pos_sign.eq(~op.sign)
            m.d.av_comb += common_case.eq((~op.is_inf) & (~op.is_zero) & (~op.is_nan))
            m.d.av_comb += op_norm.eq(common_case & (op.exp > 0))
            m.d.av_comb += op_sub.eq(common_case & (op.exp == 0))
            m.d.av_comb += op_sig_nan.eq(op.is_nan & (~op.sig[-2]))

            result = Signal(10)
            with m.If(neg_sign):
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
            with m.If(op.is_nan & (~op_sig_nan)):
                m.d.av_comb += result.eq(FPUClasses.QUIET_NAN)
            with m.Elif(op.is_nan & op_sig_nan):
                m.d.av_comb += result.eq(FPUClasses.SIG_NAN)

            return {
                "result": result,
                "errors": 0,
            }

        return m
