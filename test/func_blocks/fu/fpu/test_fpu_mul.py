from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32
from test.func_blocks.fu.fpu.fpu_test_common import SF_F32, FPUTester, SoftFloatReference
from transactron.testing import *
from test.func_blocks.fu.fpu.mul_test_cases import *
from amaranth import *
import random


class TestMul(TestCaseWithSimulator):
    def test_manual(self):
        params = IEEE754_F32
        tester = FPUTester(params)
        converter = tester.converter
        m = SimpleTestCircuit(FPUMulModule(fpu_params=params))
        sfr = SoftFloatReference()

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            test_runs = 20
            seed = 42
            random.seed(seed)

            for rm in RoundingModes:
                for _ in range(test_runs):
                    float_1_raw = random.getrandbits(32)
                    float_2_raw = random.getrandbits(32)

                    (expected_raw, expected_errors) = sfr.mul(SF_F32, float_1_raw, float_2_raw, rm)
                    expected = converter.to_output_data(expected_raw, expected_errors)

                    input_dict = {
                        "op_1": converter.to_input_data(float_1_raw),
                        "op_2": converter.to_input_data(float_2_raw),
                        "rounding_mode": rm,
                    }

                    resp = await request_adapter.call(sim, input_dict)
                    assert expected == resp

        async def test_process(sim: TestbenchContext):
            await python_float_test(sim, m.mul_request)
            await tester.run_test_set(
                rna_cases_mul,
                rna_cases_mul_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_AWAY},
                sim,
                m.mul_request,
            )
            await tester.run_test_set(
                rne_cases_mul,
                rne_cases_mul_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN},
                sim,
                m.mul_request,
            )
            await tester.run_test_set(
                rpi_cases_mul,
                rpi_cases_mul_resp,
                {"rounding_mode": RoundingModes.ROUND_UP},
                sim,
                m.mul_request,
            )
            await tester.run_test_set(
                rni_cases_mul,
                rni_cases_mul_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN},
                sim,
                m.mul_request,
            )
            await tester.run_test_set(
                rz_cases_mul,
                rz_cases_mul_resp,
                {"rounding_mode": RoundingModes.ROUND_ZERO},
                sim,
                m.mul_request,
            )
            await tester.run_test_set(
                edge_cases_mul,
                edge_cases_mul_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_AWAY},
                sim,
                m.mul_request,
            )

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
