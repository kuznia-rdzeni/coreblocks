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

        self.far_path_in_layout = [
            ("r_sign", 1)("sig_a", fpu_params.sig_width),
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
            ("out_sig", fpu_params.sig_width + 1),
            ("output_round", 1),
            ("output_sticky", 1),
        ]


class FarPathModule(Elaboratable):
    """Far Path module

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
        output_sig_add_1_check = Signal(self.params.sig_width + 1)
        output_sig = Signal(self.params.sig_width + 1)
        output_exp = Signal(self.params.exp_width + 1)

        output_round_bit = Signal()
        output_sticky_bit = Signal()
        final_guard_bit = Signal()
        final_round_bit = Signal()
        final_sticky_bit = Signal()

        round_up_inc_1  = Signal()
        round_down_inc_1 = Signal()
        round_to_inf_special_case = Signal()
        xor_sig = Signal(self.params.sig_width)
        carry_sig = Signal(self.params.sig_width)
        carry_add1 = Signal()
        rgs_any = Signal()
        rgs_all = Signal()

        # No right shift
        NRS = Signal()
        # One right shift
        ORS = Signal()
        # No left shift
        NLS = Signal()
        # One left shift
        OLS = Signal()
        NXS = Signal()

        NXS_list = [None for _ in range(RoundingModes)]
        ORS_list = [None for _ in range(RoundingModes)]
        OLS_list = [None for _ in range(RoundingModes)]

        Shift_in_bit = [None for _ in range(RoundingModes)]

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
            # TODO double check for round_up and round_down
            m.d.av_comb += input_sig_add_0_a.eq(sig_a)
            m.d.av_comb += input_sig_add_0_b.eq(sig_b)
            m.d.av_comb += xor_sig.eq(sig_a ^ sig_b)
            m.d.av_comb += carry_sig.eq(sig_a & sig_b)
            m.d.av_comb += carry_add1.eq(carry_sig[-1])
            m.d.av_comb += rgs_any.eq(guard_bit | round_bit | sticky_bit)
            m.d.av_comb += rgs_all.eq(guard_bit & round_bit & sticky_bit)
            m.d.av_comb += output_sig_add_1_check.eq(sig_a + sig_b + 1)
            m.d.av_comb += round_to_inf_special_case.eq((~sub_op) &
                ((rounding_mode == RoundingModes.ROUND_DOWN)
                | (rounding_mode == RoundingModes.ROUND_UP)))

            with m.If( round_to_inf_special_case
            ):
                m.d.av_comb += input_sig_add_1_a.eq((carry_sig << 1) | (~xor_sig[0]))
                m.d.av_comb += input_sig_add_1_b.eq(xor_sig)
            with m.Else():
                m.d.av_comb += input_sig_add_1_a.eq(sig_a)
                m.d.av_comb += input_sig_add_1_b.eq(sig_b)
                m.d.av_comb += carry_add1.eq(0)

            m.d.av_comb += output_sig_add_0.eq(input_sig_add_0_a + input_sig_add_0_b)
            m.d.av_comb += output_sig_add_1.eq(input_sig_add_1_a + input_sig_add_1_b + 1)
            m.d.av_comb += output_sig_add_1[-1].eq(output_sig_add_1[-1] | carry_add1)

            m.d.av_comb += NRS.eq((~sig_op) & (~output_sig_add_0[-1]))
            m.d.av_comb += ORS.eq((~sig_op) & (output_sig_add_0[-1]))
            m.d.av_comb += NLS.eq(
                sig_op
                & (
                    ((~rgs_any) & output_sig_add_1_check[-2])
                    | (rgs_any & output_sig_add_0[-2])
                )
            )
            m.d.av_comb += OLS.eq(
                sig_op
                & (
                    ((~rgs_any) & (~output_sig_add_1_check[-2]))
                    | (rgs_any & (~output_sig_add_0[-2]))
                )
            )
            m.d.av_comb += NXS.eq(NLS | NRS)

            subtraction = sub_op & ((~r_sign) | (~rgs_any))
            addition = (~sub_op) & ((sig_a[0] ^ sig_b[0]) & ((~r_sig) & (rgs_any)))
            m.d.av_comb += NXS_list[RoundingModes.ROUND_UP].eq(subtraction | addition)

            subtraction = sub_op & (r_sign | (~rgs_any))
            addition = (~sub_op) & ((sig_a[0] ^ sig_b[0]) & (r_sig & (rgs_any)))
            m.d.av_comb += NXS_list[RoundingModes.ROUND_DOWN].eq(subtraction | addition)

            m.d.av_comb += NXS_list[RoundingModes.ROUND_ZERO].eq(sub_op & (~rgs_any))

            subtraction = sub_op & (
                (~guard_bit)
                | (guard_bit & (~round_bit) & (~sticky_bit) & (sig_a[0] ^ sig_b[0]))
            )
            addition = (
                (~sub_op) & guard_bit & (round_bit | sticky_bit | (sig_a[0] ^ sig_b[0]))
            )
            m.d.av_comb += NXS_list[RoundingModes.ROUND_NEAREST_EVEN].eq(
                subtraction | addition
            )

            subtraction = sub_op & ((~guard_bit) ^ ((~round_bit) & (~sticky_bit)))
            addition = (~sub_op) & guard_bit
            m.d.av_comb += NXS_list[RoundingModes.ROUND_NEAREST_AWAY].eq(
                subtraction | addition
            )

            m.d.av_comb += ORS_list[RoundingModes.ROUND_UP].eq(
                (~r_sign) & ((sig_a[0] ^ sig_b[0]) | rgs_any)
            )
            m.d.av_comb += ORS_list[RoundingModes.ROUND_DOWN].eq(
                r_sign & ((sig_a[0] ^ sig_b[0]) | rgs_any)
            )
            m.d.av_comb += ORS_list[RoundingModes.ROUND_ZERO].eq(sub_op & (~rgs_any))
            m.d.av_comb += ORS_list[RoundingModes.ROUND_NEAREST_EVEN].eq(
                (sig_a[0] ^ sig_b[0]) & (rgs_any | (sig_a[1] ^ sig_b[1]))
            )
            m.d.av_comb += ORS_list[RoundingModes.ROUND_NEAREST_AWAY].eq(
                sig_a[0] ^ sig_b[0]
            )

            m.d.av_comb += OLS_list[RoundingModes.ROUND_UP].eq(
                ((~r_sign) & (~guard_bit)) | (r_sign & (~rgs_any))
            )
            m.d.av_comb += OLS_list[RoundingModes.ROUND_DOWN].eq(
                (r_sign & (~guard_bit)) | (~(r_sign) & (~rgs_any))
            )
            m.d.av_comb += OLS_list[RoundingModes.ROUND_ZERO].eq(sub_op & (~rgs_any))
            m.d.av_comb += OLS_list[RoundingModes.ROUND_NEAREST_EVEN].eq(
                (~guard_bit) & ((~round_bit) | (~sticky_bit))
            )
            m.d.av_comb += OLS_list[RoundingModes.ROUND_NEAREST_AWAY].eq(
                (~guard_bit) & ((~round_bit) | (~sticky_bit))
            )

            m.d.av_comb += Shift_in_bit[RoundingModes.ROUND_UP].eq(
                ((~r_sign) & guard_bit)
                | (
                    r_sign
                    & (
                        (guard_bit & (~round_bit) & (~sticky_bit))
                        | ((~guard_bit) & (round_bit | sticky_bit))
                    )
                )
            )
            m.d.av_comb += Shift_in_bit[RoundingModes.ROUND_DOWN].eq(
                (r_sign & guard_bit)
                | (
                    (~r_sign)
                    & (
                        (guard_bit & (~round_bit) & (~sticky_bit))
                        | ((~guard_bit) & (round_bit | sticky_bit))
                    )
                )
            )
            m.d.av_comb += Shift_in_bit[RoundingModes.ROUND_ZERO].eq(
                ((~guard_bit) & (round_bit | sticky_bit))
                | (guard_bit & (~round_bit) & (~sticky_bit))
            )
            m.d.av_comb += Shift_in_bit[RoundingModes.ROUND_NEAREST_EVEN].eq(
                ((~guard_bit) & round_bit & sticky_bit) | (guard_bit & (~round_bit))
            )
            m.d.av_comb += Shift_in_bit[RoundingModes.ROUND_NEAREST_AWAY].eq(
                ((~guard_bit) & round_bit & sticky_bit)
                | (guard_bit & (~(round_bit & sticky_bit)))
            )

            m.d.av_comb += g.eq(
                (ORS & ORS_list[rounding_mode])
                | (NXS & NXS_list)
                | (OLS & OLS_list[rounding_mode])
            )

            m.d.av_comb += round_up_inc_1.eq(rounding_mode.ROUND_UP & NRS & (~g) & (~(sig_a[0] ^ sig_b[0])) & ((~r_sig) & (rgs_any)))
            m.d.av_comb += round_down_inc_1.eq(rounding_mode.ROUND_DOWN & NRS & (~g) & (~(sig_a[0] ^ sig_b[0])) & (r_sig & (rgs_any)))
            
            with m.If(g):
                m.d.av_comb += output_sig.eq(output_sig_add_1)
            with m.Else():
                m.d.av_comb += output_sig.eq(output_sig_add_0)
            m.d.av_comb += output_exp.eq(exp)

            with m.If(round_down_inc_1 | round_down_inc_1):
                m.d.av_comb += output_sig.eq(output_sig | 1)

            with m.If(sub_op):
                m.d.av_comb += final_guard_bit.eq(
                    (~guard_bit) ^ ((~round_bit) & (~sticky_bit))
                )
                m.d.av_comb += final_round_bit.eq((~round_bit) ^ (~sticky_bit))
                m.d.av_comb += final_sticky_bit.eq(sticky_bit)

            with m.Else():
                m.d.av_comb += final_guard_bit.eq(guard_bit)
                m.d.av_comb += final_round_bit.eq(round_bit)
                m.d.av_comb += final_sticky_bit.eq(sticky_bit)

            with m.If(ORS):
                m.d.av_comb += output_sticky_bit.eq(
                    final_guard_bit | final_round_bit | final_sticky_bit
                )
                m.d.av_comb += output_round_bit.eq(sig_a[0] ^ sig_b[0])
            with m.Elif(OLS):
                m.d.av_comb += output_sticky_bit.eq(final_sticky_bit)
                m.d.av_comb += output_round_bit.eq(final_round_bit)
            with m.Else():
                m.d.av_comb += output_sticky_bit.eq(final_round_bit | final_sticky_bit)
                m.d.av_comb += output_round_bit.eq(final_guard_bit)

            with m.If((~sub_op) & output_sig[-1]):
                m.d.av_comb += output_sig.eq(output_sig >> 1)
                m.d.av_comb += output_exp.eq(output_exp + 1)

            with m.If(sub_op & (~output_sig[-2])):
                m.d.av_comb += output_sig.eq(output_sig << 1)
                m.d.av_comb += output_exp.eq(output_exp - 1)

            return {
                "out_exp": output_exp,
                "out_sig": output_sig,
                "output_round_bit": output_round_bit,
                "output_sticky_bit": output_sticky_bit,
            }
