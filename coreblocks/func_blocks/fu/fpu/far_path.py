from amaranth import *
from transactron import TModule, Method, def_method
from coreblocks.func_blocks.fu.fpu.fpu_common import RoundingModes, FPUParams


class FarPathMethodLayout:
    """Far path module layouts for methods

    Parameters
    ----------
    fpu_params; FPUParams
        FPU parameters
    """

    def __init__(self, *, fpu_params: FPUParams):
        """
        r_sign - result sign
        sig_a - significand of first operand (for effective subtraction in two's complement form)
        sig_b - significand of second operand (for effective subtraction in two's complement form)
        exp - exponent of result before shift
        sub_op - effective operation. 1 for subtraction 0 for addition
        rounding_mode - rounding mode
        guard_bit - guard bit (pth bit of second significand where p is precision)
        round_bit - round bit ((p+1)th bit of second significand where p is precision)
        sticky_bit - sticky_bit
        (OR of all bits with index >=p of second significand where p is precision)
        """
        self.far_path_in_layout = [
            ("r_sign", 1),
            ("sig_a", fpu_params.sig_width),
            ("sig_b", fpu_params.sig_width),
            ("exp", fpu_params.exp_width),
            ("sub_op", 1),
            ("rounding_mode", RoundingModes),
            ("guard_bit", 1),
            ("round_bit", 1),
            ("sticky_bit", 1),
        ]
        self.far_path_out_layout = [
            ("out_exp", fpu_params.exp_width),
            ("out_sig", fpu_params.sig_width),
            ("output_round", 1),
            ("output_sticky", 1),
        ]


class FarPathModule(Elaboratable):
    """Far Path module
    Based on: https://userpages.cs.umbc.edu/phatak/645/supl/lza/lza-survey-arith01.pdf.
    This module implements far path of adder/subtractor.
    It performs subtraction for operands whose exponent differs by more than 1 and addition
    for all combinations of operands. Besides addition it also performs rounding at the same time
    as addition using two adders (one producing a+b and second one producing a+b+1). The correct
    output is chosen by flags that differ for each rounding mode. To deal with certain
    complication that may arise during addition in certain rounding modes the input of second
    may be either input operand or (a & b)<<1 and (a^b). This allows second adder to compute
    a+b+2 in special cases that are better explained in paper linked above.

    Parameters
    ----------
    fpu_params: FPUParams
        FPU rounding module parameters

    Attributes
    ----------
    far_path_request: Method
        Transactional method for initiating far path computation.
        Takes 'far_path_in_layout' as argument.
        Returns result as 'far_path_out_layout'.
    """

    def __init__(self, *, fpu_params: FPUParams):

        self.params = fpu_params
        self.method_layouts = FarPathMethodLayout(fpu_params=self.params)
        self.far_path_request = Method(
            i=self.method_layouts.far_path_in_layout,
            o=self.method_layouts.far_path_out_layout,
        )

    def elaborate(self, platform):
        m = TModule()

        input_sig_add_0_a = Signal(self.params.sig_width)
        input_sig_add_0_b = Signal(self.params.sig_width)
        input_sig_add_1_a = Signal(self.params.sig_width)
        input_sig_add_1_b = Signal(self.params.sig_width)
        output_sig_add_0 = Signal(self.params.sig_width + 1)
        output_sig_add_1 = Signal(self.params.sig_width + 1)
        output_sig = Signal(self.params.sig_width + 1)
        output_exp = Signal(self.params.exp_width + 1)
        output_final_exp = Signal(self.params.exp_width)
        output_final_sig = Signal(self.params.sig_width)

        output_round_bit = Signal()
        output_sticky_bit = Signal()
        final_guard_bit = Signal()
        final_round_bit = Signal()
        final_sticky_bit = Signal()

        round_up_inc_1 = Signal()
        round_down_inc_1 = Signal()
        round_to_inf_special_case = Signal()
        xor_sig = Signal(self.params.sig_width)
        carry_sig = Signal(self.params.sig_width)
        carry_add1 = Signal()
        rgs_any = Signal()
        rgs_all = Signal()

        # No right shift
        nrs = Signal()
        # One right shift
        ors = Signal()
        # No left shift
        nls = Signal()
        # One left shift
        ols = Signal()
        nxs = Signal()

        nxs_rtne = Signal()
        nxs_rtna = Signal()
        nxs_zero = Signal()
        nxs_up = Signal()
        nxs_down = Signal()

        ors_rtne = Signal()
        ors_rtna = Signal()
        ors_zero = Signal()
        ors_up = Signal()
        ors_down = Signal()

        ols_rtne = Signal()
        ols_rtna = Signal()
        ols_zero = Signal()
        ols_up = Signal()
        ols_down = Signal()

        shift_in_bit_rtne = Signal()
        shift_in_bit_rtna = Signal()
        shift_in_bit_zero = Signal()
        shift_in_bit_up = Signal()
        shift_in_bit_down = Signal()
        shift_in_bit = Signal()

        g = Signal()

        @def_method(m, self.far_path_request)
        def _(
            r_sign,
            sig_a,
            sig_b,
            exp,
            sub_op,
            rounding_mode,
            guard_bit,
            round_bit,
            sticky_bit,
        ):
            m.d.av_comb += input_sig_add_0_a.eq(sig_a)
            m.d.av_comb += input_sig_add_0_b.eq(sig_b)
            m.d.av_comb += xor_sig.eq(sig_a ^ sig_b)
            m.d.av_comb += carry_sig.eq(sig_a & sig_b)
            m.d.av_comb += carry_add1.eq(carry_sig[-1])
            m.d.av_comb += rgs_any.eq(guard_bit | round_bit | sticky_bit)
            m.d.av_comb += rgs_all.eq(guard_bit & round_bit & sticky_bit)
            m.d.av_comb += round_to_inf_special_case.eq(
                (~sub_op) & ((rounding_mode == RoundingModes.ROUND_DOWN) | (rounding_mode == RoundingModes.ROUND_UP))
            )

            with m.If(round_to_inf_special_case):
                m.d.av_comb += input_sig_add_1_a.eq((carry_sig << 1) | (~xor_sig[0]))
                m.d.av_comb += input_sig_add_1_b.eq(xor_sig)
            with m.Else():
                m.d.av_comb += input_sig_add_1_a.eq(sig_a)
                m.d.av_comb += input_sig_add_1_b.eq(sig_b)
                m.d.av_comb += carry_add1.eq(0)

            m.d.av_comb += output_sig_add_0.eq(input_sig_add_0_a + input_sig_add_0_b)
            m.d.av_comb += output_sig_add_1.eq(
                (input_sig_add_1_a + input_sig_add_1_b + 1) | (carry_add1 << (self.params.sig_width - 1))
            )

            m.d.av_comb += nrs.eq((~sub_op) & (~output_sig_add_0[-1]))
            m.d.av_comb += ors.eq((~sub_op) & (output_sig_add_0[-1]))
            m.d.av_comb += nls.eq(sub_op & (((~rgs_any) & output_sig_add_1[-2]) | (rgs_any & output_sig_add_0[-2])))
            m.d.av_comb += ols.eq(
                sub_op & (((~rgs_any) & (~output_sig_add_1[-2])) | (rgs_any & (~output_sig_add_0[-2])))
            )
            m.d.av_comb += nxs.eq(nls | nrs)

            subtraction = sub_op & ((~r_sign) | (~rgs_any))
            addition = (~sub_op) & ((sig_a[0] ^ sig_b[0]) & ((~r_sign) & (rgs_any)))
            m.d.av_comb += nxs_up.eq(subtraction | addition)

            subtraction = sub_op & (r_sign | (~rgs_any))
            addition = (~sub_op) & ((sig_a[0] ^ sig_b[0]) & (r_sign & (rgs_any)))
            m.d.av_comb += nxs_down.eq(subtraction | addition)

            m.d.av_comb += nxs_zero.eq(sub_op & (~rgs_any))

            subtraction = sub_op & ((~guard_bit) | (guard_bit & (~round_bit) & (~sticky_bit) & (sig_a[0] ^ sig_b[0])))
            addition = (~sub_op) & guard_bit & (round_bit | sticky_bit | (sig_a[0] ^ sig_b[0]))
            m.d.av_comb += nxs_rtne.eq(subtraction | addition)

            subtraction = sub_op & (((~guard_bit) ^ ((~round_bit) & (~sticky_bit))) | (~rgs_any))
            addition = (~sub_op) & guard_bit
            m.d.av_comb += nxs_rtna.eq(subtraction | addition)

            m.d.av_comb += ors_up.eq((~r_sign) & ((sig_a[0] ^ sig_b[0]) | rgs_any))
            m.d.av_comb += ors_down.eq(r_sign & ((sig_a[0] ^ sig_b[0]) | rgs_any))
            m.d.av_comb += ors_zero.eq(sub_op & (~rgs_any))
            m.d.av_comb += ors_rtne.eq((sig_a[0] ^ sig_b[0]) & (rgs_any | (sig_a[1] ^ sig_b[1])))
            m.d.av_comb += ors_rtna.eq(sig_a[0] ^ sig_b[0])

            m.d.av_comb += ols_up.eq(((~r_sign) & (~guard_bit)) | (r_sign & (~rgs_any)))
            m.d.av_comb += ols_down.eq((r_sign & (~guard_bit)) | ((~r_sign) & (~rgs_any)))
            m.d.av_comb += ols_zero.eq(sub_op & (~rgs_any))
            m.d.av_comb += ols_rtne.eq((~guard_bit) & ((~round_bit) | (~sticky_bit)))
            m.d.av_comb += ols_rtna.eq((~guard_bit) & ((~round_bit) | (~sticky_bit)))
            m.d.av_comb += shift_in_bit_up.eq(
                ((~r_sign) & guard_bit)
                | (r_sign & ((guard_bit & (~round_bit) & (~sticky_bit)) | ((~guard_bit) & (round_bit | sticky_bit))))
            )
            m.d.av_comb += shift_in_bit_down.eq(
                (r_sign & guard_bit)
                | ((~r_sign) & ((guard_bit & (~round_bit) & (~sticky_bit)) | ((~guard_bit) & (round_bit | sticky_bit))))
            )
            m.d.av_comb += shift_in_bit_zero.eq(
                ((~guard_bit) & (round_bit | sticky_bit)) | (guard_bit & (~round_bit) & (~sticky_bit))
            )
            m.d.av_comb += shift_in_bit_rtne.eq(((~guard_bit) & round_bit & sticky_bit) | (guard_bit & (~round_bit)))
            m.d.av_comb += shift_in_bit_rtna.eq(
                ((~guard_bit) & round_bit & sticky_bit) | (guard_bit & (~(round_bit & sticky_bit)))
            )

            with m.Switch(rounding_mode):
                with m.Case(RoundingModes.ROUND_UP):
                    m.d.av_comb += g.eq((ors & ors_up) | (nxs & nxs_up) | (ols & ols_up))
                    m.d.av_comb += shift_in_bit.eq(shift_in_bit_up)
                with m.Case(RoundingModes.ROUND_DOWN):
                    m.d.av_comb += g.eq((ors & ors_down) | (nxs & nxs_down) | (ols & ols_down))
                    m.d.av_comb += shift_in_bit.eq(shift_in_bit_down)
                with m.Case(RoundingModes.ROUND_ZERO):
                    m.d.av_comb += g.eq((ors & ors_zero) | (nxs & nxs_zero) | (ols & ols_zero))
                    m.d.av_comb += shift_in_bit.eq(shift_in_bit_zero)

                with m.Case(RoundingModes.ROUND_NEAREST_EVEN):
                    m.d.av_comb += g.eq((ors & ors_rtne) | (nxs & nxs_rtne) | (ols & ols_rtne))
                    m.d.av_comb += shift_in_bit.eq(shift_in_bit_rtne)

                with m.Case(RoundingModes.ROUND_NEAREST_AWAY):
                    m.d.av_comb += g.eq((ors & ors_rtna) | (nxs & nxs_rtna) | (ols & ols_rtna))
                    m.d.av_comb += shift_in_bit.eq(shift_in_bit_rtna)

            m.d.av_comb += round_up_inc_1.eq(
                (rounding_mode == RoundingModes.ROUND_UP)
                & nrs
                & (~g)
                & (~(sig_a[0] ^ sig_b[0]))
                & ((~r_sign) & (rgs_any))
            )
            m.d.av_comb += round_down_inc_1.eq(
                (rounding_mode == RoundingModes.ROUND_DOWN)
                & nrs
                & (~g)
                & (~(sig_a[0] ^ sig_b[0]))
                & (r_sign & (rgs_any))
            )
            with m.If(g):
                m.d.av_comb += output_sig.eq(output_sig_add_1)
            with m.Else():
                with m.If(round_down_inc_1 | round_up_inc_1):
                    m.d.av_comb += output_sig.eq(output_sig_add_0 | 1)
                with m.Else():
                    m.d.av_comb += output_sig.eq(output_sig_add_0)
            m.d.av_comb += output_exp.eq(exp)

            with m.If(sub_op):
                m.d.av_comb += final_guard_bit.eq((~guard_bit) ^ ((~round_bit) & (~sticky_bit)))
                m.d.av_comb += final_round_bit.eq((~round_bit) ^ (~sticky_bit))
                m.d.av_comb += final_sticky_bit.eq(sticky_bit)

            with m.Else():
                m.d.av_comb += final_guard_bit.eq(guard_bit)
                m.d.av_comb += final_round_bit.eq(round_bit)
                m.d.av_comb += final_sticky_bit.eq(sticky_bit)

            with m.If(ors):
                m.d.av_comb += output_sticky_bit.eq(final_guard_bit | final_round_bit | final_sticky_bit)
                m.d.av_comb += output_round_bit.eq(sig_a[0] ^ sig_b[0])
            with m.Elif(ols):
                m.d.av_comb += output_sticky_bit.eq(final_sticky_bit)
                m.d.av_comb += output_round_bit.eq(final_round_bit)
            with m.Else():
                m.d.av_comb += output_sticky_bit.eq(final_round_bit | final_sticky_bit)
                m.d.av_comb += output_round_bit.eq(final_guard_bit)

            with m.If((~sub_op) & (output_sig[-1])):
                m.d.av_comb += output_final_sig.eq(output_sig >> 1)
                m.d.av_comb += output_final_exp.eq(output_exp + 1)

            with m.Elif((sub_op & (~output_sig[-2])) & (output_exp > 0)):
                with m.If(output_exp == 1):
                    m.d.av_comb += output_final_sig.eq(output_sig)
                with m.Else():
                    m.d.av_comb += output_final_sig.eq((output_sig << 1) | shift_in_bit)
                m.d.av_comb += output_final_exp.eq(output_exp - 1)

            with m.Else():
                m.d.av_comb += output_final_sig.eq(output_sig)
                with m.If((output_exp == 0) & ((output_sig[-2]))):
                    m.d.av_comb += output_final_exp.eq(1)
                with m.Else():
                    m.d.av_comb += output_final_exp.eq(output_exp)

            return {
                "out_exp": output_final_exp,
                "out_sig": output_final_sig,
                "output_round": output_round_bit,
                "output_sticky": output_sticky_bit,
            }

        return m
