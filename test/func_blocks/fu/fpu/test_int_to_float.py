from coreblocks.func_blocks.fu.fpu.int_to_float import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, IntConversionValues, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import ToFloatConverter, python_to_float
from transactron.testing import *
from amaranth import *
import random


class TestComp(TestCaseWithSimulator):

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        int_values = IntConversionValues(int_width=64, sig_width=24, bias=127)
        converter = ToFloatConverter(params)
        itf = SimpleTestCircuit(IntToFloatModule(fpu_params=params, int_values=int_values))

        async def itf_ec_test(sim: TestbenchContext):
            input_dict = {}
            input_dict["op"] = 0
            input_dict["signed"] = 1
            input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

            resp = await itf.itf_request.call(sim, input_dict)
            assert 0 == resp["sign"]
            assert 0 == resp["exp"]
            assert 0 == resp["sig"]

            max_negative = 1 << 63
            max_negative_exp = 190
            max_negative_sig = 1 << 23

            input_dict["op"] = max_negative
            input_dict["signed"] = 1
            input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

            resp = await itf.itf_request.call(sim, input_dict)
            assert 1 == resp["sign"]
            assert max_negative_exp == resp["exp"]
            assert max_negative_sig == resp["sig"]

        async def itf_python_test(sim: TestbenchContext):
            seed = 42
            random.seed(seed)
            test_runs = 20
            for i in range(test_runs):

                input_dict = {}
                op = random.randint(-(2 ** (63)), 2 ** (64) - 1)
                expected_resp = converter.from_float(python_to_float(op))

                input_dict["op"] = op
                input_dict["signed"] = 0 if op >= 0 else 1
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                resp = await itf.itf_request.call(sim, input_dict)

                assert expected_resp["sign"] == resp["sign"]
                assert expected_resp["exp"] == resp["exp"]
                assert expected_resp["sig"] == resp["sig"]

        async def test_process(sim: TestbenchContext):
            await itf_python_test(sim)
            await itf_ec_test(sim)

        with self.run_simulation(itf) as sim:
            sim.add_testbench(test_process)
