from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import FPUTester, FenvRm, fenv_rm_to_fpu_rm
from transactron.testing import *
from amaranth import *
import random
import struct
import ctypes
libm = ctypes.CDLL('libm.so.6')

class TestMul(TestCaseWithSimulator):
    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        tester = FPUTester(params)
        m = SimpleTestCircuit(FPUMulModule(fpu_params=params))

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            seed = 42
            random.seed(seed)
            test_runs = 20
            for fenv_rm in FenvRm:
                print(fenv_rm)
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


        async def test_process(sim: TestbenchContext):
            await python_float_test(sim, m.mul_request)

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
