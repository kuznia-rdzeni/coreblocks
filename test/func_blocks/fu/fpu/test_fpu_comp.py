from coreblocks.func_blocks.fu.fpu.fpu_comp import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, ComparisionTypes
from transactron.testing import *
from amaranth import *


class TValues:
    def __init__(self):
        self.pos_sign = 0
        self.neg_sign = 1
        self.smaller_mag = {
            "sign": self.neg_sign,
            "sig": 0b111111111101111111111110,
            "exp": 0b00000011,
            "is_inf": 0,
            "is_nan": 0,
            "is_zero": 0,
        }
        self.bigger_mag = {
            "sign": self.neg_sign,
            "sig": 0b111111111101111111111111,
            "exp": 0b00000011,
            "is_inf": 0,
            "is_nan": 0,
            "is_zero": 0,
        }
        self.zero = {
            "sign": self.neg_sign,
            "sig": 0b000000000000000000000000,
            "exp": 0b00000000,
            "is_inf": 0,
            "is_nan": 0,
            "is_zero": 1,
        }
        self.qnan = {
            "sign": self.neg_sign,
            "sig": 0b110000000000000000000000,
            "exp": 0b11111111,
            "is_inf": 0,
            "is_nan": 1,
            "is_zero": 0,
        }
        self.snan = {
            "sign": self.neg_sign,
            "sig": 0b101000000000000000000000,
            "exp": 0b11111111,
            "is_inf": 0,
            "is_nan": 1,
            "is_zero": 0,
        }
        self.inf = {
            "sign": self.neg_sign,
            "sig": 0b100000000000000000000000,
            "exp": 0b11111111,
            "is_inf": 1,
            "is_nan": 0,
            "is_zero": 0,
        }


class TestComp(TestCaseWithSimulator):

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        comp = SimpleTestCircuit(FPUCompModule(fpu_params=params))
        tv = TValues()

        async def comp_test(sim: TestbenchContext):
            op_1 = 0
            op_2 = 1
            op_1_sign = 2
            op_2_sign = 3
            lt_result = 4
            eq_result = 5
            invalid = 6
            eq_invalid = 7

            t = 1
            f = 0

            lt = ComparisionTypes.LT
            eq = ComparisionTypes.EQ
            le = ComparisionTypes.LE
            operations = [eq, le, lt]

            test_cases = [
                # Case 1 gt, neg sign
                [tv.smaller_mag, tv.bigger_mag, tv.neg_sign, tv.neg_sign, f, f, f, f],
                # Case 2 lt, neg sign
                [tv.bigger_mag, tv.smaller_mag, tv.neg_sign, tv.neg_sign, t, f, f, f],
                # Case 3 lt, pos sign
                [tv.smaller_mag, tv.bigger_mag, tv.pos_sign, tv.pos_sign, t, f, f, f],
                # Case 4 gt, pos sign
                [tv.bigger_mag, tv.smaller_mag, tv.pos_sign, tv.pos_sign, f, f, f, f],
                # Case 5 eq
                [tv.bigger_mag, tv.bigger_mag, tv.pos_sign, tv.pos_sign, f, t, f, f],
                # Case 6 pos zero, lt
                [tv.zero, tv.smaller_mag, tv.pos_sign, tv.pos_sign, t, f, f, f],
                # Case 7 pos zero, gt
                [tv.zero, tv.smaller_mag, tv.pos_sign, tv.neg_sign, f, f, f, f],
                # Case 8 neg zero, gt
                [tv.zero, tv.smaller_mag, tv.neg_sign, tv.neg_sign, f, f, f, f],
                # Case 9 neg zero, lt
                [tv.zero, tv.smaller_mag, tv.neg_sign, tv.pos_sign, t, f, f, f],
                # Case 10 pos inf, lt
                [tv.smaller_mag, tv.inf, tv.pos_sign, tv.pos_sign, t, f, f, f],
                # Case 11 pos inf, lt
                [tv.smaller_mag, tv.inf, tv.neg_sign, tv.pos_sign, t, f, f, f],
                # Case 12 neg inf, gt
                [tv.smaller_mag, tv.inf, tv.neg_sign, tv.neg_sign, f, f, f, f],
                # Case 13 neg inf, gt
                [tv.smaller_mag, tv.inf, tv.pos_sign, tv.neg_sign, f, f, f, f],
                # Case 14 both zero, same sign
                [tv.zero, tv.zero, tv.pos_sign, tv.pos_sign, f, t, f, f],
                # Case 15 both zero, diff sign
                [tv.zero, tv.zero, tv.neg_sign, tv.pos_sign, f, t, f, f],
                # Case 16 both inf, same sign
                [tv.inf, tv.inf, tv.pos_sign, tv.pos_sign, f, t, f, f],
                # Case 17 both inf, diff sign
                [tv.inf, tv.inf, tv.neg_sign, tv.pos_sign, t, f, f, f],
                # Case 18 one qnan
                [tv.qnan, tv.smaller_mag, tv.neg_sign, tv.pos_sign, f, f, t, f],
                # Case 19 two qnan
                [tv.qnan, tv.qnan, tv.neg_sign, tv.pos_sign, f, f, t, f],
                # Case 20 snan
                [tv.snan, tv.qnan, tv.neg_sign, tv.pos_sign, f, f, t, t],
            ]
            input_dict = {"op_1": {}, "op_2": {}, "operation": ComparisionTypes.LT}
            for test_case in test_cases:
                input_dict["op_1"] = test_case[op_1].copy()
                input_dict["op_2"] = test_case[op_2].copy()
                input_dict["op_1"]["sign"] = test_case[op_1_sign]
                input_dict["op_2"]["sign"] = test_case[op_2_sign]
                for operation in operations:
                    input_dict["operation"] = operation
                    resp = await comp.comp_request.call(sim, input_dict)
                    exp_result = f
                    exp_exceptions = 0
                    match operation:
                        case ComparisionTypes.EQ:
                            exp_result = test_case[eq_result]
                            exp_exceptions = Errors.INVALID_OPERATION if test_case[eq_invalid] else 0
                        case ComparisionTypes.LT:
                            exp_result = test_case[lt_result]
                            exp_exceptions = Errors.INVALID_OPERATION if test_case[invalid] else 0
                        case ComparisionTypes.LE:
                            exp_result = test_case[lt_result] | test_case[eq_result]
                            exp_exceptions = Errors.INVALID_OPERATION if test_case[invalid] else 0
                    assert resp["result"] == exp_result
                    assert resp["errors"] == exp_exceptions

        async def test_process(sim: TestbenchContext):
            await comp_test(sim)

        with self.run_simulation(comp) as sim:
            sim.add_testbench(test_process)
