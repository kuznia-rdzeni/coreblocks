from coreblocks.func_blocks.fu.fpu.far_path import *
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
)
from transactron import TModule
from transactron.lib import AdapterTrans
from transactron.testing import *
from amaranth import *


class TestFarPath(TestCaseWithSimulator):
    class FarPathModule(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.fp = fp = self.far_path = FarPathModule(fpu_params=self.params)
            m.submodules.compute = self.far_path_request_adapter = TestbenchIO(AdapterTrans(fp.far_path_request))
            return m

    params = FPUParams(sig_width=24, exp_width=8)

    def test_far_path_addition(self):
        params = FPUParams(sig_width=24, exp_width=8)
        far_path = TestFarPath.FarPathModule(params)

        async def test_ors(sim: TestbenchContext):
            test_cases = [
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000001,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000001,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000001,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000011,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
            ]
            expected_results = [
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000010,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000001,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 11,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 1,
                },
            ]
            for i in range(len(test_cases)):
                resp = await far_path.far_path_request_adapter.call(sim, test_cases[i])
                assert resp.out_exp == expected_results[i]["out_exp"]
                assert resp.out_sig == expected_results[i]["out_sig"]
                assert resp.output_round == expected_results[i]["output_round"]
                assert resp.output_sticky == expected_results[i]["output_sticky"]

        async def test_nrs(sim: TestbenchContext):
            test_cases = [
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b000000000000000000000001,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
            ]

            expected_results = [
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000001,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000010,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000001,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000001,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000010,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000000,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000010,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000001,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000000,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000001,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000010,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b111110000000000000000001,
                    "output_round": 0,
                    "output_sticky": 1,
                },
            ]
            for i in range(len(test_cases)):
                resp = await far_path.far_path_request_adapter.call(sim, test_cases[i])
                assert resp.out_exp == expected_results[i]["out_exp"]
                assert resp.out_sig == expected_results[i]["out_sig"]
                assert resp.output_round == expected_results[i]["output_round"]
                assert resp.output_sticky == expected_results[i]["output_sticky"]

        async def test_ols(sim: TestbenchContext):
            test_cases = [
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                # ROUND_DOWN
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                # ROUND_ZERO
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                # ROUND_TO_NEAREST_TIE_TO_EVEN
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 1,
                },
                # ROUND_TO_NEAREST_TIES_TO_AWAY
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000111010101000,
                    "sig_b": 0b100000000000010101000001,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
            ]
            expected_results = [
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010010,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                # ROUND_DOWN
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010010,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                # ROUND_ZERO
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010010,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                # ROUND_TO_NEAREST_TIE_TO_AWAY
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010010,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                # ROUND_TO_NEAREST_TIES_TO_AWAY
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010010,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010011,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 9,
                    "out_sig": 0b111100000010011111010100,
                    "output_round": 1,
                    "output_sticky": 0,
                },
            ]
            for i in range(len(test_cases)):
                resp = await far_path.far_path_request_adapter.call(sim, test_cases[i])
                assert resp.out_exp == expected_results[i]["out_exp"]
                assert resp.out_sig == expected_results[i]["out_sig"]
                assert resp.output_round == expected_results[i]["output_round"]
                assert resp.output_sticky == expected_results[i]["output_sticky"]

        async def test_nls(sim: TestbenchContext):
            test_cases = [
                # ROUND_UP
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                # ROUND_DOWN
                {
                    "r_sign": 0,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 0,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                # ROUND_ZERO
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_ZERO,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                # ROUND_TO_NEAREST_TIES_TO_EVEN
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111110,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                # ROUND_TO_NEAREST_TIES_TO_AWAY
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111110,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 10,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_AWAY,
                    "guard_bit": 0,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
            ]

            expected_results = [
                {
                    "out_exp": 10,
                    "out_sig": 0b101111111111111111111111,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                # ROUND_DOWN
                {
                    "out_exp": 10,
                    "out_sig": 0b101111111111111111111111,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                # ROUND_ZERO
                {
                    "out_exp": 10,
                    "out_sig": 0b101111111111111111111111,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                # ROUND_TO_NEAREST_TIES_TO_EVEN
                {
                    "out_exp": 10,
                    "out_sig": 0b101111111111111111111110,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                # ROUND_TO_NEAREST_TIES_TO_AWAY
                {
                    "out_exp": 10,
                    "out_sig": 0b101111111111111111111110,
                    "output_round": 0,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 10,
                    "out_sig": 0b110000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
            ]

            for i in range(len(test_cases)):
                resp = await far_path.far_path_request_adapter.call(sim, test_cases[i])
                assert resp.out_exp == expected_results[i]["out_exp"]
                assert resp.out_sig == expected_results[i]["out_sig"]
                assert resp.output_round == expected_results[i]["output_round"]
                assert resp.output_sticky == expected_results[i]["output_sticky"]

        async def test_special(sim: TestbenchContext):
            test_cases = [
                # overflow
                {
                    "r_sign": 1,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b100000000000000000000000,
                    "exp": (2 ** (self.params.exp_width) - 2),
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                # add zero
                {
                    "r_sign": 1,
                    "sig_a": 0b000000000000000000000000,
                    "sig_b": 0b000000000000000000000000,
                    "exp": 0,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                # Subnormal become normalized
                {
                    "r_sign": 1,
                    "sig_a": 0b010000000000000000000000,
                    "sig_b": 0b001111111111111111111111,
                    "exp": 0,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 0,
                },
                # add subnormals
                {
                    "r_sign": 0,
                    "sig_a": 0b010000000000000000000000,
                    "sig_b": 0b000000000000010100000000,
                    "exp": 0,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit": 1,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
                # add subnormal to normal
                {
                    "r_sign": 0,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b000000000000010100000000,
                    "exp": 1,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 1,
                    "round_bit": 1,
                    "sticky_bit": 1,
                },
                # sub subnormal from normal
                {
                    "r_sign": 0,
                    "sig_a": 0b100000000000000000000001,
                    "sig_b": 0b111111111111111111111110,
                    "exp": 3,
                    "sub_op": 1,
                    "rounding_mode": RoundingModes.ROUND_DOWN,
                    "guard_bit": 0,
                    "round_bit": 0,
                    "sticky_bit": 0,
                },
            ]

            expected_results = [
                {
                    "out_exp": (2 ** (self.params.exp_width) - 1),
                    "out_sig": 0b101000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 0,
                    "out_sig": 0b000000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 1,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 0,
                    "out_sig": 0b010000000000010100000001,
                    "output_round": 1,
                    "output_sticky": 0,
                },
                {
                    "out_exp": 1,
                    "out_sig": 0b110000000000010100000000,
                    "output_round": 1,
                    "output_sticky": 1,
                },
                {
                    "out_exp": 3,
                    "out_sig": 0b100000000000000000000000,
                    "output_round": 0,
                    "output_sticky": 0,
                },
            ]

            for i in range(len(test_cases)):
                resp = await far_path.far_path_request_adapter.call(sim, test_cases[i])
                assert resp.out_exp == expected_results[i]["out_exp"]
                assert resp.out_sig == expected_results[i]["out_sig"]
                assert resp.output_round == expected_results[i]["output_round"]
                assert resp.output_sticky == expected_results[i]["output_sticky"]

        async def test_process(sim: TestbenchContext):
            await test_ors(sim)
            await test_nrs(sim)
            await test_ols(sim)
            await test_nls(sim)
            await test_special(sim)

        with self.run_simulation(far_path) as sim:
            sim.add_testbench(test_process)
