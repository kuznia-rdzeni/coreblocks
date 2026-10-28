from coreblocks.func_blocks.fu.fpu.int_to_float import *
from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32, IntConversionValues, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import SF_F32, SF_I64, SF_UI64, FloatConverter, SoftFloatReference
from transactron.testing import *
from amaranth import *
import random


class TestComp(TestCaseWithSimulator):

    def test_manual(self):
        params = IEEE754_F32
        int_values = IntConversionValues(int_width=64, sig_width=24, bias=127)
        converter = FloatConverter(params)
        itf = SimpleTestCircuit(IntToFloatModule(fpu_params=params, int_values=int_values))
        sfr = SoftFloatReference()

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
            rm = RoundingModes.ROUND_NEAREST_EVEN
            seed = 42
            random.seed(seed)
            test_runs = 20

            for _ in range(test_runs):
                is_signed = random.binomialvariate()
                input = random.getrandbits(64)

                in_fmt = SF_I64 if is_signed else SF_UI64

                (expected_raw, expected_errors) = sfr.convert(in_fmt, SF_F32, input, rm)
                expected = converter.to_output_data(expected_raw, expected_errors)

                input_dict = {
                    "op": input,
                    "signed": 1 if is_signed else 0,
                    "rounding_mode": rm,
                }

                resp = await itf.itf_request.call(sim, input_dict)
                assert expected == resp

        async def test_process(sim: TestbenchContext):
            await itf_python_test(sim)
            await itf_ec_test(sim)

        with self.run_simulation(itf) as sim:
            sim.add_testbench(test_process)
