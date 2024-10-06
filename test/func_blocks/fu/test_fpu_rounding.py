from coreblocks.func_blocks.fu.fpu.fpu_rounding_module import *
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    FPURoundingParams,
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
            self.input_not_rounded = FPURoundingParams(fpu_params=self.params, is_rounded=False)
            self.input_rounded_params = FPURoundingParams(
                fpu_params=self.params,
                is_rounded=True,
            )

        def elaborate(self, platform):
            m = TModule()
            m.submodules.fpur = fpur = self.fpu_rounding = FPUrounding(fpu_rounding_params=self.input_not_rounded)
            m.submodules.fpur_rounded = fpur_rounded = self.fpu_rounding_input_rounded = FPUrounding(
                fpu_rounding_params=self.input_rounded_params
            )
            m.submodules.rounding = self.rounding_request_adapter = TestbenchIO(AdapterTrans(fpur.rounding_request))
            m.submodules.input_rounded_rounding = self.input_rounded_rounding_request_adapter = TestbenchIO(
                AdapterTrans(fpur_rounded.rounding_request)
            )

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

    @parameterized.expand([(params, help_values)])
    def test_special_cases(self, params: FPUParams, help_values: HelpValues):
        fpurt = TestFPURounding.FPURoundingModule(params)

        def other_cases_test(request_adapter: TestbenchIO, is_input_not_rounded: bool):
            test_cases = [
                # No errors
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # inexact
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # underflow rounding
                {
                    "sign": 0,
                    "sig": help_values.sub_norm_sig if is_input_not_rounded else help_values.sub_norm_sig + 1,
                    "exp": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # underflow no rounding
                {
                    "sign": 0,
                    "sig": 0,
                    "exp": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # invalid operation
                {
                    "sign": 0,
                    "sig": help_values.qnan,
                    "exp": help_values.max_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 1,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # division by zero
                {
                    "sign": 0,
                    "sig": 0,
                    "exp": help_values.max_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 1,
                    "input_inf": 0,
                },
                # overflow but no round and sticky bits
                {
                    "sign": 0,
                    "sig": 0,
                    "exp": help_values.max_exp,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # tininess but no underflow
                {
                    "sign": 0,
                    "sig": help_values.sub_norm_sig,
                    "exp": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # one of inputs was qnan
                {
                    "sign": 0,
                    "sig": help_values.qnan,
                    "exp": help_values.max_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # one of inputs was inf
                {
                    "sign": 1,
                    "sig": 0,
                    "exp": help_values.max_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 1,
                },
                # subnormal number become normalized after rounding
                {
                    "sign": 1,
                    "sig": help_values.max_sub_norm_sig,
                    "exp": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
            ]

            expected_results = [
                # No errors
                {"sign": 0, "sig": help_values.not_max_norm_even_sig, "exp": help_values.not_max_norm_exp, "errors": 0},
                # inexact
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                # underflow rounding
                {"sign": 0, "sig": help_values.sub_norm_sig + 1, "exp": 0, "errors": 24},
                # underflow no rounding
                {"sign": 0, "sig": 0, "exp": 0, "errors": 24},
                # invalid operation
                {"sign": 0, "sig": help_values.qnan, "exp": help_values.max_exp, "errors": 1},
                # division by zero
                {"sign": 0, "sig": 0, "exp": help_values.max_exp, "errors": 2},
                # overflow but no round and sticky bits
                {"sign": 0, "sig": 0, "exp": help_values.max_exp, "errors": 20},
                # tininess but no underflow
                {"sign": 0, "sig": help_values.sub_norm_sig, "exp": 0, "errors": 0},
                # one of inputs was qnan
                {"sign": 0, "sig": help_values.qnan, "exp": help_values.max_exp, "errors": 0},
                # one of inputs was inf
                {"sign": 1, "sig": 0, "exp": help_values.max_exp, "errors": 0},
                # subnormal number become normalized after rounding
                {"sign": 1, "sig": help_values.max_sub_norm_sig + 1, "exp": 1, "errors": 16},
            ]

            num_of_test_cases = len(test_cases) if is_input_not_rounded else len(test_cases) - 1

            for i in range(num_of_test_cases):

                resp = yield from request_adapter.call(test_cases[i])
                assert resp["sign"] == expected_results[i]["sign"]
                assert resp["exp"] == expected_results[i]["exp"]
                assert resp["sig"] == expected_results[i]["sig"]
                assert resp["errors"] == expected_results[i]["errors"]

        def test_process():
            yield from other_cases_test(fpurt.rounding_request_adapter, True)
            yield from other_cases_test(fpurt.input_rounded_rounding_request_adapter, False)

        with self.run_simulation(fpurt) as sim:
            sim.add_sync_process(test_process)

    @parameterized.expand(
        [
            (
                params,
                help_values,
                RoundingModes.ROUND_NEAREST_EVEN,
                tie_to_away_inc_array,
                0,
                help_values.max_exp,
                0,
                help_values.max_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_NEAREST_AWAY,
                tie_to_away_inc_array,
                0,
                help_values.max_exp,
                0,
                help_values.max_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_UP,
                round_up_inc_array,
                0,
                help_values.max_exp,
                help_values.max_sig,
                help_values.max_norm_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_DOWN,
                round_down_inc_array,
                help_values.max_sig,
                help_values.max_norm_exp,
                0,
                help_values.max_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_ZERO,
                round_zero_inc_array,
                help_values.max_sig,
                help_values.max_norm_exp,
                help_values.max_sig,
                help_values.max_norm_exp,
            ),
        ]
    )
    def test_rounding(
        self,
        params: FPUParams,
        help_values: HelpValues,
        rm: RoundingModes,
        inc_arr: list,
        plus_overflow_sig: int,
        plus_overflow_exp: int,
        minus_overflow_sig: int,
        minus_overflow_exp: int,
    ):
        fpurt = TestFPURounding.FPURoundingModule(params)

        def one_rounding_mode_test(
            request_adapter: TestbenchIO,
            is_input_not_rounded: bool,
        ):
            test_cases = [
                # overflow detection
                {
                    "sign": 0,
                    "sig": (
                        help_values.max_sig
                        if is_input_not_rounded and rm != RoundingModes.ROUND_DOWN and rm != RoundingModes.ROUND_ZERO
                        else 0
                    ),
                    "exp": (
                        help_values.max_norm_exp
                        if is_input_not_rounded and rm != RoundingModes.ROUND_DOWN and rm != RoundingModes.ROUND_ZERO
                        else help_values.max_exp
                    ),
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 1,
                    "sig": (
                        help_values.max_sig
                        if is_input_not_rounded and rm != RoundingModes.ROUND_UP and rm != RoundingModes.ROUND_ZERO
                        else 0
                    ),
                    "exp": (
                        help_values.max_norm_exp
                        if is_input_not_rounded and rm != RoundingModes.ROUND_UP and rm != RoundingModes.ROUND_ZERO
                        else help_values.max_exp
                    ),
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # no overflow 00
                {
                    "sign": 0,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[0]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 1,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[4]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # no overflow 10
                {
                    "sign": 0,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[1]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 1,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[5]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # no overflow 01
                {
                    "sign": 0,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[2]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 1,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[6]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 0,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # no overflow 11
                {
                    "sign": 0,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[3]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 1,
                    "sig": (
                        help_values.not_max_norm_sig
                        if is_input_not_rounded
                        else help_values.not_max_norm_sig + inc_arr[7]
                    ),
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 1,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # Round to nearest tie to even
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "round_bit": 1,
                    "sticky_bit": 0,
                    "rounding_mode": rm,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
            ]
            expected_results = [
                # overflow detection
                {"sign": 0, "sig": plus_overflow_sig, "exp": plus_overflow_exp, "errors": 20},
                {"sign": 1, "sig": minus_overflow_sig, "exp": minus_overflow_exp, "errors": 20},
                # no overflow 00
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig + inc_arr[0],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 0,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig + inc_arr[4],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 0,
                },
                # no overflow 01
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig + inc_arr[1],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig + inc_arr[5],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                # no overflow 10
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig + inc_arr[2],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig + inc_arr[6],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                # no overflow 11
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_sig + inc_arr[3],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_sig + inc_arr[7],
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                # Round to nearest tie to even
                {
                    "sign": 1,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "errors": 16,
                },
            ]

            num_of_test_cases = len(test_cases) if rm == RoundingModes.ROUND_NEAREST_EVEN else len(test_cases) - 2

            for i in range(num_of_test_cases):

                resp = yield from request_adapter.call(test_cases[i])
                print(i)
                assert resp["sign"] == expected_results[i]["sign"]
                assert resp["exp"] == expected_results[i]["exp"]
                assert resp["sig"] == expected_results[i]["sig"]
                assert resp["errors"] == expected_results[i]["errors"]

        def test_process():
            yield from one_rounding_mode_test(fpurt.rounding_request_adapter, True)
            yield from one_rounding_mode_test(fpurt.input_rounded_rounding_request_adapter, False)

        with self.run_simulation(fpurt) as sim:
            sim.add_sync_process(test_process)
