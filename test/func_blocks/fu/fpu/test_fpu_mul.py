from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from test.func_blocks.fu.fpu.fpu_test_common import FPUTester, FenvRm, fenv_rm_to_fpu_rm
from transactron.testing import *
from test.func_blocks.fu.fpu.mul_test_cases import *
from amaranth import *
import random
import struct
import ctypes

libm = ctypes.CDLL("libm.so.6")


class TestMul(TestCaseWithSimulator):
    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        tester = FPUTester(params)
        m = SimpleTestCircuit(FPUMulModule(fpu_params=params))

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            seed = 42
            random.seed(seed)
            test_runs = 20
            old_rm = libm.fegetround()
            for fenv_rm in FenvRm:
                libm.fesetround(fenv_rm.value)
                fpu_rm = fenv_rm_to_fpu_rm(fenv_rm)
                for i in range(test_runs):

                    input_dict = {}

                    float_1 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**3))))[0]
                    float_2 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**3))))[0]
                    hex_1 = hex(struct.unpack("<I", struct.pack("<f", float_1))[0])
                    hex_2 = hex(struct.unpack("<I", struct.pack("<f", float_2))[0])
                    result = float_1 * float_2
                    hex_result = hex(struct.unpack("<I", struct.pack("<f", result))[0])

                    input_dict["op_1"] = tester.converter.from_hex(hex_1)
                    input_dict["op_2"] = tester.converter.from_hex(hex_2)
                    input_dict["rounding_mode"] = fpu_rm

                    result = tester.converter.from_hex(hex_result)
                    resp = await request_adapter.call(sim, input_dict)

                    assert result["sign"] == resp["sign"]
                    assert result["exp"] == resp["exp"]
                    assert result["sig"] == resp["sig"]
            libm.fesetround(old_rm)

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
