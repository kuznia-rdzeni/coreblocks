from coreblocks.func_blocks.fu.fpu.close_path import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from transactron import TModule
from transactron.lib import AdapterTrans
from transactron.testing import *
from amaranth import *


class TestClosePath(TestCaseWithSimulator):
    class ClosePathModuleTest(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.close = close_path = self.close_path_module = ClosePathModule(fpu_params=self.params)
            m.submodules.request = self.close_path_request_adapter = TestbenchIO(
                AdapterTrans(close_path.close_path_request)
            )
            return m

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        close_path = TestClosePath.ClosePathModuleTest(params)

        async def normal_cases(sim: TestbenchContext):
            test_cases = [
                {  # case 1 zero adder no shift
                    "sig_a": 0b111110000000000000000000,
                    "sig_b": 0b100011000000000000000000,
                    "guard_bit": 1,
                },
                {  # case 2 one adder no shift
                    "sig_a": 0b111110000000000000000001,
                    "sig_b": 0b100011111100000000000000,
                    "guard_bit": 1,
                },
                {  # case 3 zero adder shift
                    "sig_a": 0b110010000000000000000000,
                    "sig_b": 0b010010000000000000000000,
                    "guard_bit": 1,
                },
                {  # case 4 one adder shift
                    "sig_a": 0b110010000000000000000000,
                    "sig_b": 0b010010000000000000000000,
                    "guard_bit": 0,
                },
                {  # case 5 correction shift needed
                    "sig_a": 0b100000000000000000000000,
                    "sig_b": 0b100000100000000000000000,
                    "guard_bit": 1,
                },
            ]
            expected_results = [
                {
                    "out_exp": 100,
                    "out_sig": 0b100001000000000000000000,
                    "output_round": 1,
                    "zero": 0,
                },
                {"out_exp": 100, "out_sig": 0b100001111100000000000010, "output_round": 1, "zero": 0},  # case 2
                {"out_exp": 97, "out_sig": 0b100000000000000000000100, "output_round": 0, "zero": 0},  # case 3
                {"out_exp": 97, "out_sig": 0b100000000000000000001000, "output_round": 0, "zero": 0},  # case 4
                {"out_exp": 94, "out_sig": 0b100000000000000000100000, "output_round": 0, "zero": 0},  # case 5
            ]

            for rm in RoundingModes:
                for i in range(5):
                    if rm == RoundingModes.ROUND_NEAREST_AWAY:
                        if i == 0:
                            continue
                    input_dict = {
                        "r_sign": 1 if rm == RoundingModes.ROUND_DOWN else 0,
                        "sig_a": test_cases[i]["sig_a"],
                        "sig_b": test_cases[i]["sig_b"],
                        "exp": 100,
                        "rounding_mode": rm,
                        "guard_bit": test_cases[i]["guard_bit"],
                    }
                    if rm == RoundingModes.ROUND_UP and i == 0:
                        input_dict["r_sign"] = 1
                    if rm == RoundingModes.ROUND_DOWN and i == 0:
                        input_dict["r_sign"] = 0
                    if rm == RoundingModes.ROUND_ZERO and i == 1:
                        input_dict["guard_bit"] = 0

                    resp = await close_path.close_path_request_adapter.call(sim, input_dict)
                    assert resp["out_sig"] == expected_results[i]["out_sig"]
                    assert resp["out_exp"] == expected_results[i]["out_exp"]
                    if rm == RoundingModes.ROUND_ZERO and i == 1:
                        assert resp["output_round"] == 0
                    else:
                        assert resp["output_round"] == expected_results[i]["output_round"]
                    assert resp["zero"] == expected_results[i]["zero"]

        async def corner_cases(sim: TestbenchContext):
            test_cases = [
                {  # case 1 result becomes subnormal
                    "r_sign": 0,
                    "sig_a": 0b100100000000000000000000,
                    "sig_b": 0b100011000000000000000000,
                    "exp": 1,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                },
                {  # case 2 subtract two subnormals
                    "r_sign": 0,
                    "sig_a": 0b000001100000000000000000,
                    "sig_b": 0b111111000000000000000000,
                    "exp": 0,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                },
                {  # case 3 subtract subnormal from normal
                    "r_sign": 0,
                    "sig_a": 0b110000000000000000000000,
                    "sig_b": 0b111110000010000000000000,
                    "exp": 100,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                },
                {  # case 4 shift correction turns number into subnormal
                    "r_sign": 0,
                    "sig_a": 0b100000000000000000000000,
                    "sig_b": 0b100000100000000000000000,
                    "exp": 6,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                },
                {  # case 5 large shift
                    "r_sign": 0,
                    "sig_a": 0b100000000000000000000000,
                    "sig_b": 0b100000000000000000000000,
                    "exp": 100,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 1,
                },
                {  # case 6 subtract zero
                    "r_sign": 0,
                    "sig_a": 0b100000100000000000000000,
                    "sig_b": 0b111111111111111111111111,
                    "exp": 100,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                },
                {  # case 7 result is zero
                    "r_sign": 0,
                    "sig_a": 0b100000000011000000000000,
                    "sig_b": 0b011111111100111111111111,
                    "exp": 100,
                    "rounding_mode": RoundingModes.ROUND_NEAREST_EVEN,
                    "guard_bit": 0,
                },
            ]
            expected_results = [
                {
                    "out_exp": 0,
                    "out_sig": 0b000111000000000000000001,
                    "output_round": 0,
                    "zero": 0,
                },
                {"out_exp": 0, "out_sig": 0b000000100000000000000000, "output_round": 1, "zero": 0},  # case 2
                {"out_exp": 100, "out_sig": 0b101110000010000000000001, "output_round": 0, "zero": 0},  # case 3
                {"out_exp": 0, "out_sig": 0b010000000000000000010000, "output_round": 0, "zero": 0},  # case 4
                {"out_exp": 76, "out_sig": 0b100000000000000000000000, "output_round": 0, "zero": 0},  # case 5
                {"out_exp": 100, "out_sig": 0b100000100000000000000000, "output_round": 0, "zero": 0},  # case 6
                {"out_exp": 0, "out_sig": 0b000000000000000000000000, "output_round": 0, "zero": 1},  # case 7
            ]
            for i in range(len(test_cases)):
                resp = await close_path.close_path_request_adapter.call(sim, test_cases[i])
                assert resp["out_sig"] == expected_results[i]["out_sig"]
                assert resp["out_exp"] == expected_results[i]["out_exp"]
                assert resp["output_round"] == expected_results[i]["output_round"]
                assert resp["zero"] == expected_results[i]["zero"]

        async def test_process(sim: TestbenchContext):
            await normal_cases(sim)
            await corner_cases(sim)

        with self.run_simulation(close_path) as sim:
            sim.add_testbench(test_process)
