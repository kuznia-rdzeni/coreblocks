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
            input_values_dict = {}
            input_values_dict["sign"] = 0
            input_values_dict["sig"] = help_values.not_max_norm_even_sig
            input_values_dict["exp"] = help_values.not_max_norm_exp
            input_values_dict["round_bit"] = 0
            input_values_dict["sticky_bit"] = 0
            input_values_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_AWAY
            input_values_dict["invalid_operation"] = 0
            input_values_dict["division_by_zero"] = 0
            input_values_dict["input_inf"] = 0

            # No errors
            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 0

            # inexact
            input_values_dict["sticky_bit"] = 1

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 16

            # underflow rounding
            input_values_dict["exp"] = 0
            input_values_dict["sig"] = (
                help_values.sub_norm_sig if is_input_not_rounded else help_values.sub_norm_sig + 1
            )
            input_values_dict["round_bit"] = 1

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == 0
            assert resp["sig"] == help_values.sub_norm_sig + 1
            assert resp["errors"] == 24

            # underflow no rounding

            input_values_dict["round_bit"] = 0
            input_values_dict["sig"] = 0

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == 0
            assert resp["sig"] == 0
            assert resp["errors"] == 24

            # invalid operation

            input_values_dict["exp"] = help_values.max_exp
            input_values_dict["sig"] = help_values.qnan
            input_values_dict["invalid_operation"] = 1
            input_values_dict["division_by_zero"] = 0

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == input_values_dict["sign"]
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 1

            # division by zero

            input_values_dict["exp"] = help_values.max_exp
            input_values_dict["sig"] = 0
            input_values_dict["invalid_operation"] = 0
            input_values_dict["division_by_zero"] = 1

            resp = yield from request_adapter.call(input_values_dict)
            assert resp["sign"] == input_values_dict["sign"]
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 2

            # overflow but no guard and sticky bits

            input_values_dict["round_bit"] = 0
            input_values_dict["sticky_bit"] = 0
            input_values_dict["invalid_operation"] = 0
            input_values_dict["division_by_zero"] = 0

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 20

            # tininess but no underflow

            input_values_dict["exp"] = 0
            input_values_dict["sig"] = help_values.sub_norm_sig

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 0

            # one of inputs was qnan

            input_values_dict["exp"] = help_values.max_exp
            input_values_dict["sig"] = help_values.qnan
            input_values_dict["sticky_bit"] = 1
            input_values_dict["input_inf"] = 0

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 0
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 0

            # one of inputs was inf

            input_values_dict["sign"] = 1
            input_values_dict["exp"] = help_values.max_exp
            input_values_dict["sig"] = 0
            input_values_dict["input_inf"] = 1

            resp = yield from request_adapter.call(input_values_dict)

            assert resp["sign"] == 1
            assert resp["exp"] == input_values_dict["exp"]
            assert resp["sig"] == input_values_dict["sig"]
            assert resp["errors"] == 0

            # subnormal number become normalized after rounding

            if is_input_not_rounded:
                input_values_dict["exp"] = 0
                input_values_dict["sig"] = help_values.max_sub_norm_sig
                input_values_dict["sticky_bit"] = 1
                input_values_dict["round_bit"] = 1
                input_values_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_AWAY
                input_values_dict["input_inf"] = 0

                resp = yield from request_adapter.call(input_values_dict)
                assert resp["sign"] == 1
                assert resp["exp"] == 1
                assert resp["sig"] == input_values_dict["sig"] + 1
                assert resp["errors"] == 16

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
        plus_oveflow_sig: int,
        plus_overflow_exp: int,
        minus_overflow_sig: int,
        minus_overflow_exp: int,
    ):
        fpurt = TestFPURounding.FPURoundingModule(params)

        def one_rounding_mode_test(
            request_adapter: TestbenchIO,
            is_input_not_rounded: bool,
        ):
            input_values_dict = {}
            input_values_dict["sign"] = 0
            input_values_dict["sig"] = (
                help_values.max_sig
                if is_input_not_rounded and rm != RoundingModes.ROUND_DOWN and rm != RoundingModes.ROUND_ZERO
                else 0
            )
            input_values_dict["exp"] = (
                help_values.max_norm_exp
                if is_input_not_rounded and rm != RoundingModes.ROUND_DOWN and rm != RoundingModes.ROUND_ZERO
                else help_values.max_exp
            )
            input_values_dict["round_bit"] = 1
            input_values_dict["sticky_bit"] = 1
            input_values_dict["rounding_mode"] = rm
            input_values_dict["invalid_operation"] = 0
            input_values_dict["division_by_zero"] = 0
            input_values_dict["input_inf"] = 0

            # overflow detection
            resp = yield from request_adapter.call(input_values_dict)
            assert resp["sign"] == 0
            assert resp["exp"] == plus_overflow_exp
            assert resp["sig"] == plus_oveflow_sig
            assert resp["errors"] == 20

            input_values_dict["sign"] = 1
            input_values_dict["sig"] = (
                help_values.max_sig
                if is_input_not_rounded and rm != RoundingModes.ROUND_UP and rm != RoundingModes.ROUND_ZERO
                else 0
            )
            input_values_dict["exp"] = (
                help_values.max_norm_exp
                if is_input_not_rounded and rm != RoundingModes.ROUND_UP and rm != RoundingModes.ROUND_ZERO
                else help_values.max_exp
            )

            resp = yield from request_adapter.call(input_values_dict)
            assert resp["sign"] == 1
            assert resp["exp"] == minus_overflow_exp
            assert resp["sig"] == minus_overflow_sig
            assert resp["errors"] == 20

            # no overflow
            input_values_dict["exp"] = help_values.not_max_norm_exp

            for i in range(4):
                input_values_dict["sign"] = 0
                input_values_dict["round_bit"] = i & 1
                input_values_dict["sticky_bit"] = (i >> 1) & 1
                input_values_dict["sig"] = (
                    help_values.not_max_norm_sig if is_input_not_rounded else help_values.not_max_norm_sig + inc_arr[i]
                )

                resp = yield from request_adapter.call(input_values_dict)
                assert resp["sign"] == 0
                assert resp["exp"] == help_values.not_max_norm_exp
                assert resp["sig"] == help_values.not_max_norm_sig + inc_arr[i]
                if i:
                    assert resp["errors"] == 16
                else:
                    assert resp["errors"] == 0

                input_values_dict["sign"] = 1
                input_values_dict["sig"] = (
                    help_values.not_max_norm_sig
                    if is_input_not_rounded
                    else help_values.not_max_norm_sig + inc_arr[4 + i]
                )

                resp = yield from request_adapter.call(input_values_dict)
                assert resp["sign"] == 1
                assert resp["exp"] == help_values.not_max_norm_exp
                assert resp["sig"] == help_values.not_max_norm_sig + inc_arr[4 + i]
                if i:
                    assert resp["errors"] == 16
                else:
                    assert resp["errors"] == 0

            if rm == RoundingModes.ROUND_NEAREST_EVEN:
                input_values_dict["sticky_bit"] = 0
                input_values_dict["round_bit"] = 1

                # tie, no increment
                input_values_dict["sign"] = 1
                input_values_dict["sig"] = help_values.not_max_norm_even_sig

                resp = yield from request_adapter.call(input_values_dict)
                assert resp["sign"] == 1
                assert resp["exp"] == help_values.not_max_norm_exp
                assert resp["sig"] == help_values.not_max_norm_even_sig
                assert resp["errors"] == 16

                input_values_dict["sign"] = 0

                resp = yield from request_adapter.call(input_values_dict)
                assert resp["sign"] == 0
                assert resp["exp"] == help_values.not_max_norm_exp
                assert resp["sig"] == help_values.not_max_norm_even_sig
                assert resp["errors"] == 16

        def test_process():
            yield from one_rounding_mode_test(fpurt.rounding_request_adapter, True)
            yield from one_rounding_mode_test(fpurt.input_rounded_rounding_request_adapter, False)

        with self.run_simulation(fpurt) as sim:
            sim.add_sync_process(test_process)
