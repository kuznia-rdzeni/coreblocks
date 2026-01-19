from coreblocks.func_blocks.fu.fpu.fpu_class import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, FPUClasses
from test.func_blocks.fu.fpu.fpu_test_common import ToFloatConverter
from transactron.testing import *
from amaranth import *
from dataclasses import dataclass


class TValues:
    def __init__(self):
        tc = ToFloatConverter(FPUParams(sig_width=24, exp_width=8))
        self.pos_sign = 0
        self.neg_sign = 1
        self.norm_sig = tc.from_hex("81FFDFFE")
        self.sub_sig = tc.from_hex("807FDFFE")
        self.zero = tc.from_hex("00000000")
        self.qnan = tc.from_hex("FFC00000")
        self.snan = tc.from_hex("FFA00000")
        self.inf = tc.from_hex("FF800000")


tv = TValues()


@dataclass
class TCase:
    op: dict[str, int]
    op_sign: int
    result: FPUClasses


test_cases = [
    # Case 1 -inf
    TCase(tv.inf, tv.neg_sign, FPUClasses.NEG_INF),
    # Case 2 -norm
    TCase(tv.norm_sig, tv.neg_sign, FPUClasses.NEG_NORM),
    # Case 3 -sub
    TCase(tv.sub_sig, tv.neg_sign, FPUClasses.NEG_SUB),
    # Case 4 -zero
    TCase(tv.zero, tv.neg_sign, FPUClasses.NEG_ZERO),
    # Case 5 +inf
    TCase(tv.inf, tv.pos_sign, FPUClasses.POS_INF),
    # Case 6 +norm
    TCase(tv.norm_sig, tv.pos_sign, FPUClasses.POS_NORM),
    # Case 7 +sub
    TCase(tv.sub_sig, tv.pos_sign, FPUClasses.POS_SUB),
    # Case 8 +zero
    TCase(tv.zero, tv.pos_sign, FPUClasses.POS_ZERO),
    # Case 9 snan
    TCase(tv.snan, tv.pos_sign, FPUClasses.SIG_NAN),
    # Case 10 qnan
    TCase(tv.qnan, tv.neg_sign, FPUClasses.QUIET_NAN),
]


class TestComp(TestCaseWithSimulator):

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        cl = SimpleTestCircuit(FPUClassModule(fpu_params=params))

        async def class_test(sim: TestbenchContext):
            input_dict = {"op": {}}
            for test_case in test_cases:
                input_dict["op"] = test_case.op
                input_dict["op"]["sign"] = test_case.op_sign
                resp = await cl.class_request.call(sim, input_dict)
                exp_result = test_case.result
                assert resp["result"] == exp_result
                assert resp["errors"] == 0

        async def test_process(sim: TestbenchContext):
            await class_test(sim)

        with self.run_simulation(cl) as sim:
            sim.add_testbench(test_process)
