from coreblocks.func_blocks.fu.fpu.fpu_rounding_module import *
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
)
from transactron import TModule
from transactron.lib import AdapterTrans
from parameterized import parameterized
from transactron.testing import *
from amaranth import *


class TestFPURounding(TestCaseWithSimulator):
    class FPURoundingModule(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.fpur = fpur = self.fpu_rounding = FPUrounding(fpu_params=self.params)
            m.submodules.rounding = self.rounding_request_adapter = TestbenchIO(AdapterTrans(fpur.rounding_request))
            return m

    class HelpValues:
        def __init__(self, params: FPUParams):
            self.params = params
            self.max_exp = (2**self.params.exp_width) - 1
            self.max_norm_exp = (2**self.params.exp_width) - 2
            self.not_max_norm_exp = (2**self.params.exp_width) - 3
            self.max_sig = (2**params.sig_width) - 1
            self.not_max_norm_sig = 1 << (self.params.sig_width - 1) | 1
            self.not_max_norm_even_sig = 1 << (self.params.sig_width - 1)
            self.sub_norm_sig = 3
            self.max_sub_norm_sig = (2 ** (self.params.sig_width - 1)) - 1
            self.qnan = 3 << (self.params.sig_width - 2) | 1

    params = FPUParams(sig_width=24, exp_width=8)
    help_values = HelpValues(params)

    tie_to_even_inc_array = [
        0,
        1,
        0,
        1,
        0,
        1,
        0,
        1,
    ]
    tie_to_away_inc_array = [0, 1, 0, 1, 0, 1, 0, 1]
    round_up_inc_array = [0, 1, 1, 1, 0, 0, 0, 0]
    round_down_inc_array = [0, 0, 0, 0, 0, 1, 1, 1]
    round_zero_inc_array = [0, 0, 0, 0, 0, 0, 0, 0]

    @parameterized.expand(
        [
            (
                params,
                help_values,
                RoundingModes.ROUND_NEAREST_EVEN,
                tie_to_away_inc_array,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_NEAREST_AWAY,
                tie_to_away_inc_array,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_UP,
                round_up_inc_array,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_DOWN,
                round_down_inc_array,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_ZERO,
                round_zero_inc_array,
            ),
        ]
    )
    def test_rounding(
        self,
        params: FPUParams,
        help_values: HelpValues,
        rm: RoundingModes,
        inc_arr: list,
    ):
        fpurt = TestFPURounding.FPURoundingModule(params)

        def one_rounding_mode_test():
            test_cases = [
                # carry after increment
                {
                    "sign": 0 if rm != RoundingModes.ROUND_DOWN else 1,
                    "sig": help_values.max_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                },
                # no overflow 00
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                },
                # no overflow 10
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                },
                # no overflow 01
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                },
                # no overflow 11
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                },
                # Round to nearest tie to even
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                },
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                },
            ]
            expected_results = [
                # carry after increment
                {
                    "sig": (help_values.max_sig + 1) >> 1 if rm != RoundingModes.ROUND_ZERO else help_values.max_sig,
                    "exp": (
                        help_values.not_max_norm_exp + 1
                        if rm != RoundingModes.ROUND_ZERO
                        else help_values.not_max_norm_exp
                    ),
                    "inexact": 1,
                },
                # no overflow 00
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[0],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 0,
                },
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[4],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 0,
                },
                # no overflow 01
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[1],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[5],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                # no overflow 10
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[2],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[6],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                # no overflow 11
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[3],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                {
                    "sig": help_values.not_max_norm_sig + inc_arr[7],
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                # Round to nearest tie to even
                {
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
                {
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 1,
                },
            ]

            num_of_test_cases = len(test_cases) if rm == RoundingModes.ROUND_NEAREST_EVEN else len(test_cases) - 2

            for i in range(num_of_test_cases):

                resp = yield from fpurt.rounding_request_adapter.call(test_cases[i])
                assert resp["exp"] == expected_results[i]["exp"]
                assert resp["sig"] == expected_results[i]["sig"]
                assert resp["inexact"] == expected_results[i]["inexact"]

        def test_process():
            yield from one_rounding_mode_test()

        with self.run_simulation(fpurt) as sim:
            sim.add_sync_process(test_process)
