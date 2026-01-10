from coreblocks.func_blocks.fu.fpu.float_to_int import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, RoundingModes, Errors
from test.func_blocks.fu.fpu.test_add_sub import ToFloatConverter
from transactron.testing import *
from amaranth import *
import struct
import random
import ctypes


class TestFTI(TestCaseWithSimulator):

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        converter = ToFloatConverter(params)
        fti = SimpleTestCircuit(FloatToIntModule(fpu_params=params, int_width=64))

        async def fti_ec_test(sim: TestbenchContext):
            max_exp = (2**8) - 1
            max_un_int = (2**64) - 1
            min_sig_int = 2**63
            max_sig_int = (2**63) - 1
            bias = 127
            test_cases = [
                # Test 1: Zero
                {
                    "input": {"sign": 0, "exp": 0, "sig": 0, "is_inf": 0, "is_nan": 0, "is_zero": 1},
                    "signed": 1,
                    "result": 0,
                    "errors": 0,
                },
                # Test 2: NaN
                {
                    "input": {"sign": 1, "exp": max_exp, "sig": 2**20, "is_inf": 0, "is_nan": 1, "is_zero": 0},
                    "signed": 0,
                    "result": max_un_int,
                    "errors": Errors.INVALID_OPERATION,
                },
                # Test 3: -Inf
                {
                    "input": {"sign": 1, "exp": max_exp, "sig": 2**23, "is_inf": 1, "is_nan": 0, "is_zero": 0},
                    "signed": 1,
                    "result": min_sig_int,
                    "errors": Errors.INVALID_OPERATION,
                },
                # Test 4: +Inf
                {
                    "input": {"sign": 0, "exp": max_exp, "sig": 2**23, "is_inf": 1, "is_nan": 0, "is_zero": 0},
                    "signed": 1,
                    "result": max_sig_int,
                    "errors": Errors.INVALID_OPERATION,
                },
                # Test 4: Rounding
                {
                    "input": {"sign": 0, "exp": bias, "sig": (2**24) - 1, "is_inf": 0, "is_nan": 0, "is_zero": 0},
                    "signed": 1,
                    "result": 2,
                    "errors": Errors.INEXACT,
                },
                # Test 5: Out of bound negative
                {
                    "input": {"sign": 1, "exp": bias + 63, "sig": (2**23) | 1, "is_inf": 0, "is_nan": 0, "is_zero": 0},
                    "signed": 1,
                    "result": min_sig_int,
                    "errors": Errors.INVALID_OPERATION,
                },
                # Test 6: Out of positive negative
                {
                    "input": {"sign": 0, "exp": bias + 63, "sig": (2**23), "is_inf": 0, "is_nan": 0, "is_zero": 0},
                    "signed": 1,
                    "result": max_sig_int,
                    "errors": Errors.INVALID_OPERATION,
                },
                # Test 7: Mag less than one, out of bound
                {
                    "input": {"sign": 1, "exp": bias - 1, "sig": (2**24) - 1, "is_inf": 0, "is_nan": 0, "is_zero": 0},
                    "signed": 0,
                    "result": 0,
                    "errors": Errors.INVALID_OPERATION,
                },
            ]

            input_dict = {}
            for tc in test_cases:
                input_dict["op"] = tc["input"]
                input_dict["signed"] = tc["signed"]
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                resp = await fti.fti_request.call(sim, input_dict)
                assert tc["result"] == resp["result"]
                assert tc["errors"] == resp["errors"]

        async def fti_python_test(sim: TestbenchContext):
            seed = 42
            random.seed(seed)
            test_runs = 20

            for i in range(test_runs):

                input_dict = {}
                op_sig = random.uniform(-(2 ** (63)), 2 ** (63) - 1)
                op_unsig = random.uniform(0, 2 ** (63))

                fl_sig = struct.unpack("f", struct.pack("f", op_sig))[0]
                fl_unsig = struct.unpack("f", struct.pack("f", op_unsig))[0]
                hex_sig = hex(struct.unpack("<I", struct.pack("<f", fl_sig))[0])
                hex_unsig = hex(struct.unpack("<I", struct.pack("<f", fl_unsig))[0])

                expected_value_sig = int(fl_sig)
                expected_value_unsig = int(fl_unsig)

                input_sig = converter.from_hex(hex_sig)
                input_unsig = converter.from_hex(hex_unsig)

                input_dict["op"] = input_sig
                input_dict["signed"] = 1
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                resp = await fti.fti_request.call(sim, input_dict)

                resp_signed = ctypes.c_int64(resp["result"]).value
                assert expected_value_sig == resp_signed

                input_dict["op"] = input_unsig
                input_dict["signed"] = 0
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                resp = await fti.fti_request.call(sim, input_dict)
                assert expected_value_unsig == resp["result"]

        async def test_process(sim: TestbenchContext):
            await fti_python_test(sim)
            await fti_ec_test(sim)

        with self.run_simulation(fti) as sim:
            sim.add_testbench(test_process)
