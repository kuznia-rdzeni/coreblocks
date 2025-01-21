from amaranth import *
from transactron import TModule, Method, def_method, Transaction
from coreblocks.func_blocks.fu.fpu.fpu_common import RoundingModes, FPUParams
from coreblocks.func_blocks.fu.fpu.lza import LZAModule


class ClosePathMethodLayout:
    """Close path module layouts for methods

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.close_path_in_layout = [
            ("r_sign", 1),
            ("sig_a", fpu_params.sig_width),
            ("sig_b", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("exp_equal", 1),
            ("rounding_mode", RoundingModes),
            ("guard_bit", 1),
        ]
        self.close_path_out_layout = [
            ("out_exp", fpu_params.exp_width),
            ("out_sig", fpu_params.sig_width),
            ("output_round", 1),
            ("zero", 1),
        ]


class ClosePathModule(Elaboratable):
    """Close path module

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    close_path_request: Method
        Transactional method for initiating close path computation.
        Takes 'close_path_in_layout' as argument.
        Returns result as 'close_path_out_layout'.
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.params = fpu_params
        self.method_layouts = ClosePathMethodLayout(fpu_params=self.params)
        self.close_path_request = Method(
            i=self.method_layouts.close_path_in_layout,
            o=self.method_layouts.close_path_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        result_add_zero = Signal(self.params.sig_width)
        result_add_one = Signal(self.params.sig_width)
        lza_shifts_zero = Signal(range(self.params.sig_width))
        lza_shifts_one = Signal(range(self.params.sig_width))
        final_result = Signal(self.params.sig_width)
        correct_shift = Signal(range(self.params.sig_width))
        shift_correction = Signal(1)
        shift_amount = Signal(range(self.params.sig_width))
        bit_shift_amount = Signal(range(self.params.sig_width))
        check_shift_amount = Signal(range(self.params.sig_width))
        shifted_sig = Signal(self.params.sig_width)
        shifted_exp = Signal(self.params.sig_width)
        final_sig = Signal(self.params.sig_width)
        final_exp = Signal(self.params.exp_width)
        final_round = Signal(1)

        rtne_l = Signal(1)
        rtna_l = Signal(1)
        zero_l = Signal(1)
        up_l = Signal(1)
        down_l = Signal(1)
        shift_in_bit = Signal(1)
        l_flag = Signal(1)
        is_zero = Signal(1)

        m.submodules.zero_lza = zero_lza = LZAModule(fpu_params=self.params)
        m.submodules.one_lza = one_lza = LZAModule(fpu_params=self.params)

        @def_method(m, self.close_path_request)
        def _(
            r_sign,
            sig_a,
            sig_b,
            exp,
            exp_equal,
            rounding_mode,
            guard_bit,
        ):
            m.d.av_comb += result_add_zero.eq(sig_a + sig_b)
            m.d.av_comb += result_add_one.eq(sig_a + sig_b + 1)
            m.d.av_comb += shift_in_bit.eq(guard_bit)

            with Transaction().body(m):
                resp = zero_lza.predict_request(m, sig_a=sig_a, sig_b=sig_b, carry=0)
                m.d.av_comb += lza_shifts_zero.eq(resp["shift_amount"])

            with Transaction().body(m):
                resp = one_lza.predict_request(m, sig_a=sig_a, sig_b=sig_b, carry=1)
                m.d.av_comb += lza_shifts_one.eq(resp["shift_amount"])

            rtne_case_one = (result_add_zero[-1] & guard_bit & result_add_zero[0]) | ~(guard_bit)
            rtne_case_two = exp_equal
            m.d.av_comb += rtne_l.eq(rtne_case_one | rtne_case_two)

            rtna_case_one = (result_add_zero[-1] & guard_bit) | ~(guard_bit)
            rtna_case_two = exp_equal
            m.d.av_comb += rtna_l.eq(rtna_case_one | rtna_case_two)

            m.d.av_comb += up_l.eq((~(r_sign) & result_add_zero[-1] & guard_bit) | ~(guard_bit))

            m.d.av_comb += down_l.eq((r_sign & result_add_zero[-1] & guard_bit) | ~(guard_bit))

            m.d.av_comb += zero_l.eq(~(guard_bit))

            with m.Switch(rounding_mode):
                with m.Case(RoundingModes.ROUND_UP):
                    m.d.av_comb += l_flag.eq(up_l)
                with m.Case(RoundingModes.ROUND_DOWN):
                    m.d.av_comb += l_flag.eq(down_l)
                with m.Case(RoundingModes.ROUND_ZERO):
                    m.d.av_comb += l_flag.eq(zero_l)
                with m.Case(RoundingModes.ROUND_NEAREST_EVEN):
                    m.d.av_comb += l_flag.eq(rtne_l)
                with m.Case(RoundingModes.ROUND_NEAREST_AWAY):
                    m.d.av_comb += l_flag.eq(rtna_l)

            with m.If(l_flag):
                m.d.av_comb += final_result.eq(result_add_one)
                m.d.av_comb += correct_shift.eq(lza_shifts_one)
            with m.Else():
                m.d.av_comb += final_result.eq(result_add_zero)
                m.d.av_comb += correct_shift.eq(lza_shifts_zero)

            with m.If((final_result == 0) & (guard_bit == 0)):
                m.d.av_comb += final_sig.eq(final_result)
                m.d.av_comb += final_exp.eq(0)
                m.d.av_comb += final_round.eq(guard_bit)
            with m.Elif(exp == 0):
                m.d.av_comb += final_sig.eq(final_result)
                m.d.av_comb += final_exp.eq(0)
                m.d.av_comb += final_round.eq(guard_bit)

            with m.Elif(exp <= correct_shift):
                with m.If(exp == 1):
                    m.d.av_comb += final_sig.eq(final_result)
                    m.d.av_comb += final_round.eq(guard_bit)
                with m.Else():
                    m.d.av_comb += shift_amount.eq((exp - 1))
                    m.d.av_comb += bit_shift_amount.eq((exp - 2))
                    m.d.av_comb += final_sig.eq((final_result << shift_amount) | (shift_in_bit << bit_shift_amount))
                    m.d.av_comb += final_round.eq(0)
                m.d.av_comb += final_exp.eq(0)

            with m.Else():
                m.d.av_comb += shifted_sig.eq(final_result << correct_shift)
                m.d.av_comb += shifted_exp.eq(exp - correct_shift)
                m.d.av_comb += check_shift_amount.eq(correct_shift - 1)
                m.d.av_comb += shift_correction.eq(
                    (shifted_sig | (guard_bit << check_shift_amount))[self.params.sig_width - 1]
                )

                with m.If(shift_correction):
                    with m.If(correct_shift == 0):
                        m.d.av_comb += final_sig.eq(shifted_sig)
                        m.d.av_comb += final_round.eq(guard_bit)
                    with m.Else():
                        m.d.av_comb += bit_shift_amount.eq(correct_shift - 1)
                        m.d.av_comb += final_sig.eq(shifted_sig | (shift_in_bit << bit_shift_amount))
                        m.d.av_comb += final_round.eq(0)
                    m.d.av_comb += final_exp.eq(shifted_exp)

                with m.Else():
                    m.d.av_comb += final_round.eq(0)
                    with m.If(shifted_exp == 1):
                        with m.If(correct_shift > 0):
                            m.d.av_comb += bit_shift_amount.eq(correct_shift - 1)
                            m.d.av_comb += final_sig.eq(shifted_sig | (shift_in_bit << bit_shift_amount))
                        with m.Else():
                            m.d.av_comb += final_sig.eq(shifted_sig)
                        m.d.av_comb += final_exp.eq(0)

                    with m.Else():
                        m.d.av_comb += final_sig.eq((shifted_sig << 1) | (shift_in_bit << (correct_shift)))
                        m.d.av_comb += final_exp.eq(shifted_exp - 1)

            sig_zero = final_sig == 0
            exp_zero = final_exp == 0
            m.d.av_comb += is_zero.eq(sig_zero & exp_zero)
            # m.d.comb += Print("sig_a: ", sig_a, " sig_b: ", sig_b)
            # m.d.comb += Print("result_zero: ",result_add_zero)
            # m.d.comb += Print("result_one: ",result_add_one)
            # m.d.comb += Print("final_result: ",final_result)
            # m.d.comb += Print("shift_amount: ", correct_shift)
            # m.d.comb += Print("shifted_result: ",shifted_sig)
            # m.d.comb += Print("shift_correction: ",shift_correction)
            # m.d.comb += Print("check:", (shifted_sig | (guard_bit << check_shift_amount)))
            # m.d.comb += Print("l value: ", l_flag)
            return {"out_exp": final_exp, "out_sig": final_sig, "output_round": final_round, "zero": is_zero}

        return m
