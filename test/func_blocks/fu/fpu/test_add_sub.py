from coreblocks.func_blocks.fu.fpu.fpu_add_sub import *
from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import SF_F32, FPUTester, SoftFloatReference
from test.func_blocks.fu.fpu.add_sub_test_cases import *
from transactron.testing import *
from amaranth import *
import random


class TestAddSub(TestCaseWithSimulator):
    def test_manual(self):
        params = IEEE754_F32
        tester = FPUTester(params)
        m = SimpleTestCircuit(FPUAddSubModule(fpu_params=params))
        sfr = SoftFloatReference()

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            rm = RoundingModes.ROUND_NEAREST_EVEN
            seed = 42
            test_runs = 5000
            random.seed(seed)

            for i in range(test_runs):
                float_1_raw = random.getrandbits(32)
                float_2_raw = random.getrandbits(32)
                test_addition = i < test_runs / 2

                if test_addition:
                    (expected_raw, expected_errors) = sfr.add(SF_F32, float_1_raw, float_2_raw, rm)
                else:
                    (expected_raw, expected_errors) = sfr.sub(SF_F32, float_1_raw, float_2_raw, rm)

                input_dict = {
                    "operation": 0 if test_addition else 1,
                    "op_1": tester.converter.to_input_data(float_1_raw),
                    "op_2": tester.converter.to_input_data(float_2_raw),
                    "rounding_mode": rm,
                }

                result = tester.converter.to_output_data(expected_raw, expected_errors)
                resp = await request_adapter.call(sim, input_dict)
                FPUTester.compare_results(result, resp)

        async def test_process(sim: TestbenchContext):
            def construct_input(test_case_data, rounding_mode: RoundingModes):
                return {
                    "operation": 0,
                    "op_1": tester.converter.to_input_data(test_case_data[0]),
                    "op_2": tester.converter.to_input_data(test_case_data[1]),
                    "rounding_mode": rounding_mode,
                }

            def get_expected(test_case_data, rounding_mode: RoundingModes):
                (expected_raw, expected_errors) = sfr.add(SF_F32, test_case_data[0], test_case_data[1], rounding_mode)
                return tester.converter.to_output_data(expected_raw, expected_errors)

            await python_float_test(sim, m.add_sub_request)
            await tester.run_test_set(
                add_sub_edge_cases,
                construct_input,
                get_expected,
                sim,
                m.add_sub_request,
            )

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
