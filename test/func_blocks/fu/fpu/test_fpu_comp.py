from coreblocks.func_blocks.fu.fpu.fpu_comp import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, ComparisionTypes
from test.func_blocks.fu.fpu.fpu_test_common import ToFloatConverter
from transactron.testing import *
from amaranth import *
from dataclasses import dataclass
from typing import TypedDict


class TValues:
    def __init__(self):
        tc = ToFloatConverter(FPUParams(sig_width=24, exp_width=8))
        self.pos_sign = 0
        self.neg_sign = 1
        self.smaller_mag = tc.from_hex("81FFDFFE")
        self.bigger_mag = tc.from_hex("81FFDFFF")
        self.zero = tc.from_hex("00000000")
        self.qnan = tc.from_hex("FFC00000")
        self.snan = tc.from_hex("FFA00000")
        self.inf = tc.from_hex("FF800000")


@dataclass
class TCase:
    lhs: TypedDict
    rhs: TypedDict
    lhs_sign: int
    rhs_sign: int
    lt_result: bool
    eq_result: bool
    invalid: bool
    eq_invalid: bool


tv = TValues()

test_cases = [
    # Case 1 gt, neg sign
    TCase(tv.smaller_mag, tv.bigger_mag, tv.neg_sign, tv.neg_sign, 0, 0, 0, 0),
    # Case 2 lt, neg sign
    TCase(tv.bigger_mag, tv.smaller_mag, tv.neg_sign, tv.neg_sign, 1, 0, 0, 0),
    # Case 3 lt, pos sign
    TCase(tv.smaller_mag, tv.bigger_mag, tv.pos_sign, tv.pos_sign, 1, 0, 0, 0),
    # Case 4 gt, pos sign
    TCase(tv.bigger_mag, tv.smaller_mag, tv.pos_sign, tv.pos_sign, 0, 0, 0, 0),
    # Case 5 eq
    TCase(tv.bigger_mag, tv.bigger_mag, tv.pos_sign, tv.pos_sign, 0, 1, 0, 0),
    # Case 6 pos zero, lt
    TCase(tv.zero, tv.smaller_mag, tv.pos_sign, tv.pos_sign, 1, 0, 0, 0),
    # Case 7 pos zero, gt
    TCase(tv.zero, tv.smaller_mag, tv.pos_sign, tv.neg_sign, 0, 0, 0, 0),
    # Case 8 neg zero, gt
    TCase(tv.zero, tv.smaller_mag, tv.neg_sign, tv.neg_sign, 0, 0, 0, 0),
    # Case 9 neg zero, lt
    TCase(tv.zero, tv.smaller_mag, tv.neg_sign, tv.pos_sign, 1, 0, 0, 0),
    # Case 10 pos inf, lt
    TCase(tv.smaller_mag, tv.inf, tv.pos_sign, tv.pos_sign, 1, 0, 0, 0),
    # Case 11 pos inf, lt
    TCase(tv.smaller_mag, tv.inf, tv.neg_sign, tv.pos_sign, 1, 0, 0, 0),
    # Case 12 neg inf, gt
    TCase(tv.smaller_mag, tv.inf, tv.neg_sign, tv.neg_sign, 0, 0, 0, 0),
    # Case 13 neg inf, gt
    TCase(tv.smaller_mag, tv.inf, tv.pos_sign, tv.neg_sign, 0, 0, 0, 0),
    # Case 14 both zero, same sign
    TCase(tv.zero, tv.zero, tv.pos_sign, tv.pos_sign, 0, 1, 0, 0),
    # Case 15 both zero, diff sign
    TCase(tv.zero, tv.zero, tv.neg_sign, tv.pos_sign, 0, 1, 0, 0),
    # Case 16 both inf, same sign
    TCase(tv.inf, tv.inf, tv.pos_sign, tv.pos_sign, 0, 1, 0, 0),
    # Case 17 both inf, diff sign
    TCase(tv.inf, tv.inf, tv.neg_sign, tv.pos_sign, 1, 0, 0, 0),
    # Case 18 one qnan
    TCase(tv.qnan, tv.smaller_mag, tv.neg_sign, tv.pos_sign, 0, 0, 1, 0),
    # Case 19 two qnan
    TCase(tv.qnan, tv.qnan, tv.neg_sign, tv.pos_sign, 0, 0, 1, 0),
    # Case 20 snan
    TCase(tv.snan, tv.qnan, tv.neg_sign, tv.pos_sign, 0, 0, 1, 1),
]


class TestComp(TestCaseWithSimulator):

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        comp = SimpleTestCircuit(FPUCompModule(fpu_params=params))

        async def comp_test(sim: TestbenchContext):
            lt = ComparisionTypes.LT
            eq = ComparisionTypes.EQ
            le = ComparisionTypes.LE
            operations = [eq, le, lt]
            input_dict = {"op_1": {}, "op_2": {}, "operation": ComparisionTypes.LT}
            for test_case in test_cases:
                input_dict["op_1"] = test_case.lhs.copy()
                input_dict["op_2"] = test_case.rhs.copy()
                input_dict["op_1"]["sign"] = test_case.lhs_sign
                input_dict["op_2"]["sign"] = test_case.rhs_sign
                for operation in operations:
                    input_dict["operation"] = operation
                    resp = await comp.comp_request.call(sim, input_dict)
                    exp_result = 0
                    exp_exceptions = 0
                    match operation:
                        case ComparisionTypes.EQ:
                            exp_result = test_case.eq_result
                            exp_exceptions = Errors.INVALID_OPERATION if test_case.eq_invalid else 0
                        case ComparisionTypes.LT:
                            exp_result = test_case.lt_result
                            exp_exceptions = Errors.INVALID_OPERATION if test_case.invalid else 0
                        case ComparisionTypes.LE:
                            exp_result = test_case.lt_result | test_case.eq_result
                            exp_exceptions = Errors.INVALID_OPERATION if test_case.invalid else 0
                    assert resp["result"] == exp_result
                    assert resp["errors"] == exp_exceptions

        async def test_process(sim: TestbenchContext):
            await comp_test(sim)

        with self.run_simulation(comp) as sim:
            sim.add_testbench(test_process)
