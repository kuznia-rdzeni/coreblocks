from coreblocks.func_blocks.fu.fpu.fpu_error_module import *
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
    Errors,
)
from transactron import TModule
from transactron.lib import AdapterTrans
from parameterized import parameterized
from transactron.testing import *
from amaranth import *


class TestFPUError(TestCaseWithSimulator):
    class FPUErrorModule(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.fpue = fpue = self.fpu_error_module = FPUErrorModule(fpu_params=self.params)
            m.submodules.error_checking = self.error_checking_request_adapter = TestbenchIO(
                AdapterTrans.create(fpue.error_checking_request)
            )
            return m

    class HelpValues:
        def __init__(self, params: FPUParams):
            self.params = params
            self.implicit_bit = 2 ** (self.params.sig_width - 1)
            self.max_exp = (2**self.params.exp_width) - 1
            self.max_norm_exp = (2**self.params.exp_width) - 2
            self.not_max_norm_exp = (2**self.params.exp_width) - 3
            self.max_sig = (2**params.sig_width) - 1
            self.not_max_norm_sig = 1 << (self.params.sig_width - 1) | 1
            self.not_max_norm_even_sig = 1 << (self.params.sig_width - 1)
            self.sub_norm_sig = 3
            self.min_norm_sig = 1 << (self.params.sig_width - 1)
            self.max_sub_norm_sig = (2 ** (self.params.sig_width - 1)) - 1
            self.qnan = 3 << (self.params.sig_width - 2) | 1

    params = FPUParams(sig_width=24, exp_width=8)
    help_values = HelpValues(params)

    @parameterized.expand([(params, help_values)])
    def test_special_cases(self, params: FPUParams, help_values: HelpValues):
        fpue = TestFPUError.FPUErrorModule(params)

        async def other_cases_test(sim: TestbenchContext):
            test_cases = [
                # No errors
                {
                    "sign": 0,
                    "sig": help_values.not_max_norm_even_sig,
                    "exp": help_values.not_max_norm_exp,
                    "inexact": 0,
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
                    "inexact": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # underflow
                {
                    "sign": 0,
                    "sig": help_values.sub_norm_sig,
                    "exp": 0,
                    "inexact": 1,
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
                    "inexact": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 1,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # division by zero
                {
                    "sign": 0,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "inexact": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 1,
                    "input_inf": 0,
                },
                # overflow but no round and sticky bits
                {
                    "sign": 0,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "inexact": 0,
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
                    "inexact": 0,
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
                    "inexact": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                # one of inputs was inf
                {
                    "sign": 1,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "inexact": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 1,
                },
                # subnormal number become normalized after rounding
                {
                    "sign": 1,
                    "sig": help_values.min_norm_sig,
                    "exp": 0,
                    "inexact": 1,
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
                    "errors": Errors.INEXACT,
                },
                # underflow
                {"sign": 0, "sig": help_values.sub_norm_sig, "exp": 0, "errors": Errors.UNDERFLOW | Errors.INEXACT},
                # invalid operation
                {"sign": 0, "sig": help_values.qnan, "exp": help_values.max_exp, "errors": Errors.INVALID_OPERATION},
                # division by zero
                {
                    "sign": 0,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "errors": Errors.DIVISION_BY_ZERO,
                },
                # overflow but no round and sticky bits
                {
                    "sign": 0,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "errors": Errors.INEXACT | Errors.OVERFLOW,
                },
                # tininess but no underflow
                {"sign": 0, "sig": help_values.sub_norm_sig, "exp": 0, "errors": 0},
                # one of inputs was qnan
                {"sign": 0, "sig": help_values.qnan, "exp": help_values.max_exp, "errors": 0},
                # one of inputs was inf
                {"sign": 1, "sig": help_values.implicit_bit, "exp": help_values.max_exp, "errors": 0},
                # subnormal number become normalized after rounding
                {"sign": 1, "sig": help_values.min_norm_sig, "exp": 1, "errors": Errors.INEXACT},
            ]
            for i in range(len(test_cases)):
                resp = await fpue.error_checking_request_adapter.call(sim, test_cases[i])
                assert resp.sign == expected_results[i]["sign"]
                assert resp.exp == expected_results[i]["exp"]
                assert resp.sig == expected_results[i]["sig"]
                assert resp.errors == expected_results[i]["errors"]

        async def test_process(sim: TestbenchContext):
            await other_cases_test(sim)

        with self.run_simulation(fpue) as sim:
            sim.add_testbench(test_process)

    @parameterized.expand(
        [
            (
                params,
                help_values,
                RoundingModes.ROUND_NEAREST_EVEN,
                help_values.implicit_bit,
                help_values.max_exp,
                help_values.implicit_bit,
                help_values.max_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_NEAREST_AWAY,
                help_values.implicit_bit,
                help_values.max_exp,
                help_values.implicit_bit,
                help_values.max_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_UP,
                help_values.implicit_bit,
                help_values.max_exp,
                help_values.max_sig,
                help_values.max_norm_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_DOWN,
                help_values.max_sig,
                help_values.max_norm_exp,
                help_values.implicit_bit,
                help_values.max_exp,
            ),
            (
                params,
                help_values,
                RoundingModes.ROUND_ZERO,
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
        plus_overflow_sig: int,
        plus_overflow_exp: int,
        minus_overflow_sig: int,
        minus_overflow_exp: int,
    ):
        fpue = TestFPUError.FPUErrorModule(params)

        async def one_rounding_mode_test(sim: TestbenchContext):
            test_cases = [
                # overflow detection
                {
                    "sign": 0,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "rounding_mode": rm,
                    "inexact": 0,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
                {
                    "sign": 1,
                    "sig": help_values.implicit_bit,
                    "exp": help_values.max_exp,
                    "rounding_mode": rm,
                    "inexact": 0,
                    "invalid_operation": 0,
                    "division_by_zero": 0,
                    "input_inf": 0,
                },
            ]
            expected_results = [
                # overflow detection
                {
                    "sign": 0,
                    "sig": plus_overflow_sig,
                    "exp": plus_overflow_exp,
                    "errors": Errors.INEXACT | Errors.OVERFLOW,
                },
                {
                    "sign": 1,
                    "sig": minus_overflow_sig,
                    "exp": minus_overflow_exp,
                    "errors": Errors.INEXACT | Errors.OVERFLOW,
                },
            ]

            for i in range(len(test_cases)):
                resp = await fpue.error_checking_request_adapter.call(sim, test_cases[i])
                assert resp["sign"] == expected_results[i]["sign"]
                assert resp["exp"] == expected_results[i]["exp"]
                assert resp["sig"] == expected_results[i]["sig"]
                assert resp["errors"] == expected_results[i]["errors"]

        async def test_process(sim: TestbenchContext):
            await one_rounding_mode_test(sim)

        with self.run_simulation(fpue) as sim:
            sim.add_testbench(test_process)
