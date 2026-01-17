from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from test.func_blocks.fu.fpu.fpu_test_common import (
    FPUTester,
    FenvRm,
    fenv_rm_to_fpu_rm,
    python_to_float,
    python_float_tester,
)
from transactron.testing import *
from test.func_blocks.fu.fpu.mul_test_cases import *
from amaranth import *
import random
import ctypes

libm = ctypes.CDLL("libm.so.6")


class TestMul(TestCaseWithSimulator):
    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        tester = FPUTester(params)
        converter = tester.converter
        m = SimpleTestCircuit(FPUMulModule(fpu_params=params))

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            test_runs = 20
            seed = 42
            with python_float_tester():
                random.seed(seed)
                for fenv_rm in FenvRm:
                    libm.fesetround(fenv_rm.value)
                    fpu_rm = fenv_rm_to_fpu_rm(fenv_rm)
                    for i in range(test_runs):
                        input_dict = {}

                        float_1 = python_to_float(random.uniform(0, 3.4028235 * (10**3)))
                        float_2 = python_to_float(random.uniform(0, 3.4028235 * (10**3)))
                        result = float_1 * float_2

                        input_dict["op_1"] = converter.from_float(float_1)
                        input_dict["op_2"] = converter.from_float(float_2)
                        input_dict["rounding_mode"] = fpu_rm

                        result = converter.from_float(result)
                        resp = await request_adapter.call(sim, input_dict)

                        assert result["sign"] == resp["sign"]
                        assert result["exp"] == resp["exp"]
                        assert result["sig"] == resp["sig"]

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
