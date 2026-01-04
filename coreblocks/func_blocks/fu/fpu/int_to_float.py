from amaranth import *
from transactron import TModule, Method, def_method
from transactron.utils.amaranth_ext import count_leading_zeros
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    FPUParams,
    RoundingModes,
    IntConversionValues,
    create_output_layout,
)

from coreblocks.func_blocks.fu.fpu.fpu_rounding_module import FPURounding


class IntToFloatMethodLayout:
    """FPU comparision module method layout

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    int_values; IntConversionValues
        Values for int to float conversion
    """

    def __init__(self, *, fpu_params: FPUParams, int_values: IntConversionValues):
        self.itf_in_layout = [
            ("op", int_values.int_width),
            ("signed", 1),
            ("rounding_mode", RoundingModes),
        ]
        """
        | Input layout for int to float conversion
        | op - layout containing data of the first integer
        | signed - bit indicating if op is signed or unsigned
        | rounding_mode - selected rounding mode
        """
        self.itf_out_layout = create_output_layout(fpu_params)
        """
        | Output layout for comparision created using
            :meth:`create_output_layout <coreblocks.func_blocks.fu.fpu.fpu_common.create_output_layout>`
        """


class IntToFloatModule(Elaboratable):
    """Module for int to float conversion
    Module responsible for performing conversion from int to float.

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters
    int_values; IntConversionValues
        Values for int to float conversion

    Attributes
    ----------
    comp_request: Method
        Transactional method for initiating comparision.
        Takes 'itf_in_layout' as argument
        Returns result as 'itf_out_layout'
    """

    def __init__(self, *, fpu_params: FPUParams, int_values: IntConversionValues):

        self.conv_params = fpu_params
        self.int_values = int_values
        self.method_layouts = FPUCompMethodLayout(fpu_params=self.conv_params, int_values=self.int_values)
        self.itf_request = Method(
            i=self.method_layouts.itf_in_layout,
            o=self.method_layouts.itf_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.rounding_module = rounding_module = FPURounding(fpu_params=self.fpu_params)

        @def_method(m, self.comp_request)
        def _(op, signed):
            is_zero = Signal()
            m.d.av_comb += is_zero.eq(op == 0)

            sign = Signal()
            m.d.av_comb += sign.eq(signed & op[-1])

            abs_ext_sig = Signal(self.int_values.ext_width)
            m.d.av_comb += abs_ext_sig.eq(Mux(sign, (-(op.as_signed())).as_unsigned(), op))

            n_shift = Signal(self.int_values.shift_width)
            m.d.av_comb += n_shift.eq(count_leading_zeros(abs_ext_sig))

            norm_ext_sig += Signal(self.int_values.ext_width)
            m.d.av_comb += norm_ext_sig.eq(abs_ext_sig << n_shift)

            round_bit = Signal()
            sticky_bit = Signal()
            m.d.av_comb += round_bit.eq(
                Mux(is_zero, 0, Mux(self.exact, 0, norm_ext_sig[self.int_values.round_bit_index]))
            )
            m.d.av_comb += sticky_bit.eq(
                Mux(is_zero, 0, Mux(self.exact, 0, norm_ext_sig[0 : self.int_values.msb_sticky_index]))
            )

            ur_norm_sig += Signal(self.conv_params.sig_width)
            ur_exp += Signal(self.conv_params.exp_width)
            shifted_ext_sig = norm_ext_sig >> self.int_values.ext_to_dst_shift
            m.d.av_comb += norm_sig.eq(Mux(is_zero, 0, Mux(self.exact, norm_ext_sig, shifted_ext_sig)))
            m.d.av_comb += ur_exp.eq(Mux(is_zero, 0, self.int_values.exp_base_value))

            resp = rounding_module.rounding_request(
                m,
                sign=sign,
                sig=ur_norm_sig,
                exp=ur_exp,
                round_bit=round_bit,
                sticky_bit=sticky_bit,
                rounding_mode=rounding_mode,
            )

            return {"sign": sign, "sig": resp["sig"], "exp": resp["exp"], "errors": resp["inexact"]}

        return m
