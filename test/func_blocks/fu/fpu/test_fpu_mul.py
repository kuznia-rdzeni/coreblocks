from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32
from test.func_blocks.fu.fpu.fpu_test_common import SF_F32, FPUTester, FloatData, SoftFloatReference
from transactron.testing import *
from test.func_blocks.fu.fpu.mul_test_cases import *
from test.func_blocks.fu.fpu.float_generator import FloatGenerator as Fg
from amaranth import *
from itertools import product
import random


class TestMul(TestCaseWithSimulator):
    def test_manual(self):
        params = IEEE754_F32
        tester = FPUTester(params)
        converter = tester.converter
        m = SimpleTestCircuit(FPUMulModule(fpu_params=params))
        sfr = SoftFloatReference()

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            test_runs = 5000
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
                    FPUTester.compare_results(resp, expected)

        async def test_process(sim: TestbenchContext):
            def construct_input(test_case_data, rounding_mode: RoundingModes):
                return {
                    "op_1": converter.to_input_data(test_case_data[0]),
                    "op_2": converter.to_input_data(test_case_data[1]),
                    "rounding_mode": rounding_mode,
                }

            def get_expected(test_case_data: list[int] | tuple[FloatData, FloatData], rounding_mode: RoundingModes):
                def to_raw(val: int | FloatData) -> int:
                    return val.to_raw_float(params) if isinstance(val, FloatData) else val

                (data_a, data_b) = (to_raw(x) for x in test_case_data)
                (expected_raw, expected_errors) = sfr.mul(SF_F32, data_a, data_b, rounding_mode)
                return converter.to_output_data(expected_raw, expected_errors)

            await python_float_test(sim, m.mul_request)
            await tester.run_test_set(
                edge_cases_mul,
                construct_input,
                get_expected,
                sim,
                m.mul_request,
            )

            await tester.run_test_set(
                product(Fg(params).common_floats, Fg(params).common_floats),
                construct_input,
                get_expected,
                sim,
                m.mul_request,
            )

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
