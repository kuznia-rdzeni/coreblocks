from coreblocks.func_blocks.fu.fpu.float_to_int import *
from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32, RoundingModes, Errors
from test.func_blocks.fu.fpu.fpu_test_common import SF_F32, SF_I64, SF_UI64, FloatConverter, SoftFloatReference
from transactron.testing import *
from amaranth import *
import random
from dataclasses import dataclass

# Few notes for later.
# 1. Due to the precision of float some conditions for out of bound numbers
# are impossible to fulfill/test due to lack of precision (both for 32 and 64 bit integers).
# Add more tests later when more precise versions of floating point numbers are available
# 2. Due to the fact that we are not using rounding module but separatly
# compute if rounding is needed, it may be worth to test all rounding modes or
# modify rounding module to return one bit of information signifying if rounding occured

converter = FloatConverter(IEEE754_F32)


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
        converter.to_input_data("00000000"),
        1,
        0,
        0,
    ),
    # Test 2: NaN
    TCase(
        converter.to_input_data("FFC00000"),
        0,
        max_un_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 3: -Inf
    TCase(
        converter.to_input_data("FF800000"),
        1,
        min_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 4: +Inf
    TCase(
        converter.to_input_data("7F800000"),
        1,
        max_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 4: Rounding
    TCase(
        converter.to_input_data("3FFFFFFF"),
        1,
        2,
        Errors.INEXACT,
    ),
    # Test 5: Out of bound negative
    TCase(
        converter.to_input_data("DF000001"),
        1,
        min_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 6: Out of bound positive
    TCase(
        converter.to_input_data("5F000000"),
        1,
        max_sig_int,
        Errors.INVALID_OPERATION,
    ),
    # Test 7: Mag less than one, out of bound
    TCase(
        converter.to_input_data("bf7fffff"),
        0,
        0,
        Errors.INVALID_OPERATION,
    ),
    # Currently broken
    # Test 8: 1.5 should round to 2
    # TCase(
    #     converter.to_input_data("3FC00000"),
    #     0,
    #     2,
    #     0
    # ),
    # Currently broken
    # Test 9: -1.5 should round to -2
    # TCase(
    #     converter.to_input_data("BFC00000"),
    #     1,
    #     max_un_int - 1,
    #     0
    # ),
]


class TestFTI(TestCaseWithSimulator):

    def test_manual(self):
        params = IEEE754_F32
        fti = SimpleTestCircuit(FloatToIntModule(fpu_params=params, int_width=64))
        sfr = SoftFloatReference()

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
            rm = RoundingModes.ROUND_NEAREST_EVEN
            seed = 42
            random.seed(seed)
            test_runs = 20

            for _ in range(test_runs):
                float_raw = random.getrandbits(32)
                input = converter.to_input_data(float_raw)

                (expected_signed, expected_signed_errors) = sfr.convert(SF_F32, SF_I64, float_raw, rm)
                input_dict = {
                    "op": input,
                    "signed": 1,
                    "rounding_mode": rm,
                }

                resp = await fti.fti_request.call(sim, input_dict)
                assert expected_signed == resp["result"]
                assert expected_signed_errors == resp["errors"]

                (expected_unsigned, expected_unsigned_errors) = sfr.convert(SF_F32, SF_UI64, float_raw, rm)
                input_dict = {
                    "op": input,
                    "signed": 0,
                    "rounding_mode": rm,
                }

                resp = await fti.fti_request.call(sim, input_dict)
                assert expected_unsigned == resp["result"]
                assert expected_unsigned_errors == resp["errors"]

        async def test_process(sim: TestbenchContext):
            # Float to Integer conversion does not work correctly
            # await fti_python_test(sim)
            await fti_ec_test(sim)

        with self.run_simulation(fti) as sim:
            sim.add_testbench(test_process)
