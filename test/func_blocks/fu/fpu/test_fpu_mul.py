from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import FPUTester
from transactron.testing import *
from amaranth import *
import random
from decimal import *
import struct
import ctypes
libm = ctypes.CDLL('libm.so.6')


FE_TONEAREST = 0x0000
FE_DOWNWARD = 0x400
FE_UPWARD = 0x800
FE_TOWARDZERO = 0xc00

class TestMul(TestCaseWithSimulator):
    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        tester = FPUTester(params)
        m = SimpleTestCircuit(FPUMulModule(fpu_params=params))

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            seed = 42
            random.seed(seed)

            getcontext().prec = 7
            getcontext().Emin = -45
            getcontext().Emax = 31

            test_runs = 20

            for i in range(test_runs):

                input_dict = {}

                float_1 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**3))))[0]
                float_2 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**3))))[0]
                hex_1 = hex(struct.unpack("<I", struct.pack("<f", float_1))[0])
                hex_2 = hex(struct.unpack("<I", struct.pack("<f", float_2))[0])
                #libm.fesetround(FE_UPWARD)
                result = float_1 * float_2
                hex_result = hex(struct.unpack("<I", struct.pack("<f", result))[0])

                input_dict["op_1"] = tester.converter.from_hex(hex_1)
                input_dict["op_2"] = tester.converter.from_hex(hex_2)
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                result = tester.converter.from_hex(hex_result)
                resp = await request_adapter.call(sim, input_dict)

                print("TEST ", i)
                print(input_dict["op_1"])
                print(input_dict["op_2"])
                print(result)
                assert result["sign"] == resp["sign"]
                assert result["exp"] == resp["exp"]
                assert result["sig"] == resp["sig"]


        async def test_process(sim: TestbenchContext):
            await python_float_test(sim, m.mul_request)

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
