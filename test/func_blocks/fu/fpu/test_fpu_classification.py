from coreblocks.func_blocks.fu.fpu.fpu_class import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, FPUClasses
from transactron.testing import *
from amaranth import *


class TValues:
    def __init__(self):
        self.pos_sign = 0
        self.neg_sign = 1
        self.norm_sig = {
            "sign": self.neg_sign,
            "sig": 0b111111111101111111111110,
            "exp": 0b00000011,
            "is_inf": 0,
            "is_nan": 0,
            "is_zero": 0,
        }
        self.sub_sig = {
            "sign": self.neg_sign,
            "sig": 0b011111111101111111111111,
            "exp": 0b00000000,
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
        cl = SimpleTestCircuit(FPUClassModule(fpu_params=params))
        tv = TValues()

        async def class_test(sim: TestbenchContext):
            op = 0
            op_sign = 1
            result = 2

            test_cases = [
                # Case 1 -inf
                [tv.inf, tv.neg_sign, FPUClasses.NEG_INF],
                # Case 2 -norm
                [tv.norm_sig, tv.neg_sign, FPUClasses.NEG_NORM],
                # Case 3 -sub
                [tv.sub_sig, tv.neg_sign, FPUClasses.NEG_SUB],
                # Case 4 -zero
                [tv.zero, tv.neg_sign, FPUClasses.NEG_ZERO],
                # Case 5 +inf
                [tv.inf, tv.pos_sign, FPUClasses.POS_INF],
                # Case 6 +norm
                [tv.norm_sig, tv.pos_sign, FPUClasses.POS_NORM],
                # Case 7 +sub
                [tv.sub_sig, tv.pos_sign, FPUClasses.POS_SUB],
                # Case 8 +zero
                [tv.zero, tv.pos_sign, FPUClasses.POS_ZERO],
                # Case 9 snan
                [tv.snan, tv.pos_sign, FPUClasses.SIG_NAN],
                # Case 10 qnan
                [tv.qnan, tv.neg_sign, FPUClasses.QUIET_NAN],
            ]
            input_dict = {"op": {}}
            for test_case in test_cases:
                input_dict["op"] = test_case[op]
                input_dict["op"]["sign"] = test_case[op_sign]
                resp = await cl.class_request.call(sim, input_dict)
                exp_result = test_case[result]
                assert resp["result"] == exp_result
                assert resp["errors"] == 0

        async def test_process(sim: TestbenchContext):
            await class_test(sim)

        with self.run_simulation(cl) as sim:
            sim.add_testbench(test_process)
