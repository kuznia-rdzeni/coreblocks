from coreblocks.func_blocks.fu.fpu.fpu_mul import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import FPUTester
from transactron.testing import *
from amaranth import *
import random
from decimal import *
import struct


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

                p_float_1 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**3))))[0]
                p_float_2 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**3))))[0]
                hex_1 = hex(struct.unpack("<I", struct.pack("<f", p_float_1))[0])
                hex_2 = hex(struct.unpack("<I", struct.pack("<f", p_float_2))[0])
                print(hex_1)
                print(hex_2)
                res = p_float_1 * p_float_2
                hex_r = hex(struct.unpack("<I", struct.pack("<f", res))[0])
                print(res)
                print(hex_r)

                assert 1 == 2

                input_dict["op_1"] = tester.converter.from_hex(hex_1)
                input_dict["op_2"] = tester.converter.from_hex(hex_2)
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                result = tester.converter.from_hex(hex_result)
                resp = await request_adapter.call(sim, input_dict)

                resp = await request_adapter.call(sim, input_dict)
                assert result["sign"] == resp["sign"]
                assert result["exp"] == resp["exp"]
                assert result["sig"] == resp["sig"]

        async def test_process(sim: TestbenchContext):
            await python_float_test(sim, m.mul_request)

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
