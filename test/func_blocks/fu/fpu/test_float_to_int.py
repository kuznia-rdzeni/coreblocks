from coreblocks.func_blocks.fu.fpu.float_to_int import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, RoundingModes, Errors
from test.func_blocks.fu.fpu.fpu_test_common import ToFloatConverter, python_to_float
from transactron.testing import *
from amaranth import *
import random
import ctypes
from dataclasses import dataclass

# Few notes for later.
# 1. Due to the precision of float some conditions for out of bound numbers
# are impossible to fulfill/test due to lack of precision (both for 32 and 64 bit integers).
# Add more tests later when more precise versions of floating point numbers are available
# 2. Due to the fact that we are not using rounding module but separatly
# compute if rounding is needed, it may be worth to test all rounding modes or
# modify rounding module to return one bit of information signifying if rounding occured

converter = ToFloatConverter(FPUParams(sig_width=24, exp_width=8))


@dataclass
class TCase:
    op: dict[str, int]
    signed: int
    result: int
    errors: int


max_un_int = (2**64) - 1
min_sig_int = 2**63
max_sig_int = (2**63) - 1

test_cases = [
    # Test 1: Zero
    TCase(
        converter.from_hex("00000000"),
        1,
        0,
        0,
    ),
    # Test 2: NaN
    TCase(
        converter.from_hex("FFC00000"),
        0,
        max_un_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 3: -Inf
    TCase(
        converter.from_hex("FF800000"),
        1,
        min_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 4: +Inf
    TCase(
        converter.from_hex("7F800000"),
        1,
        max_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 4: Rounding
    TCase(
        converter.from_hex("3FFFFFFF"),
        1,
        2,
        Errors.INEXACT,
    ),
    # Test 5: Out of bound negative
    TCase(
        converter.from_hex("DF000001"),
        1,
        min_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 6: Out of bound positive
    TCase(
        converter.from_hex("5F000000"),
        1,
        max_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 7: Mag less than one, out of bound
    TCase(
        converter.from_hex("bf7fffff"),
        0,
        0,
        Errors.INVALID_OPERATION,
    ),
]


class TestFTI(TestCaseWithSimulator):

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        fti = SimpleTestCircuit(FloatToIntModule(fpu_params=params, int_width=64))

        async def fti_ec_test(sim: TestbenchContext):
            input_dict = {}
            for tc in test_cases:
                input_dict["op"] = tc.op
                input_dict["signed"] = tc.signed
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                resp = await fti.fti_request.call(sim, input_dict)
                assert tc.result == resp["result"]
                assert tc.errors == resp["errors"]

        async def fti_python_test(sim: TestbenchContext):
            seed = 42
            random.seed(seed)
            test_runs = 20

            for i in range(test_runs):

                input_dict = {}
                op_sig = random.uniform(-(2 ** (63)), 2 ** (63) - 1)
                op_unsig = random.uniform(0, 2 ** (63))

                fl_sig = python_to_float(op_sig)
                fl_unsig = python_to_float(op_unsig)

                expected_value_sig = int(fl_sig)
                expected_value_unsig = int(fl_unsig)

                input_sig = converter.from_float(op_sig)
                input_unsig = converter.from_float(op_unsig)

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
