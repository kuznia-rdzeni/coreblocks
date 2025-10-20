from coreblocks.func_blocks.fu.fpu.fpu_sign_injection import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from transactron import TModule
from transactron.lib import AdapterTrans
from transactron.testing import *
from amaranth import *


class TestSI(TestCaseWithSimulator):
    class SIModuleTest(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.si = si = self.si_module = SIModule(fpu_params=self.params)
            m.submodules.si_request = self.si_request_adapter = TestbenchIO(AdapterTrans.create(si.si_request))
            return m

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        si = TestSI.SIModuleTest(params)

        async def si_test(sim: TestbenchContext):
            test_cases = [
                {
                    "sign_1": 1,
                    "sign_2": 0,
                    "sig_1": 0b111111111101111111111111,
                    "sig_2": 0b100001110101001100110000,
                    "exp_1": 0b11111111,
                    "exp_2": 0b00000011,
                    "operation": SIOperations.FSGNJ_S,
                    "norm_inf_nan": 2,
                },
                {
                    "sign_1": 1,
                    "sign_2": 1,
                    "sig_1": 0b111111101101111111111111,
                    "sig_2": 0b100001110101001100110000,
                    "exp_1": 0b11111110,
                    "exp_2": 0b00000011,
                    "operation": SIOperations.FSGNJX_S,
                    "norm_inf_nan": 0,
                },
                {
                    "sign_1": 1,
                    "sign_2": 0,
                    "sig_1": 0b000000000000000000000000,
                    "sig_2": 0b100001110101001100110000,
                    "exp_1": 0b11111111,
                    "exp_2": 0b00000011,
                    "operation": SIOperations.FSGNJN_S,
                    "norm_inf_nan": 1,
                },
            ]
            expected_results = [
                {"sign": 0, "sig": test_cases[0]["sig_1"], "exp": test_cases[0]["exp_1"], "errors": 0},
                {"sign": 0, "sig": test_cases[1]["sig_1"], "exp": test_cases[1]["exp_1"], "errors": 0},
                {"sign": 1, "sig": test_cases[2]["sig_1"], "exp": test_cases[2]["exp_1"], "errors": 0},
            ]
            for i in range(len(test_cases)):
                input_dict = {
                    "op_1": {
                        "sign": test_cases[i]["sign_1"],
                        "sig": test_cases[i]["sig_1"],
                        "exp": test_cases[i]["exp_1"],
                        "is_inf": test_cases[i]["norm_inf_nan"] == 1,
                        "is_nan": test_cases[i]["norm_inf_nan"] == 2,
                        "is_zero": test_cases[i]["norm_inf_nan"] == 0,
                    },
                    "op_2": {
                        "sign": test_cases[i]["sign_2"],
                        "sig": test_cases[i]["sig_2"],
                        "exp": test_cases[i]["exp_2"],
                        "is_inf": 0,
                        "is_nan": 0,
                        "is_zero": 0,
                    },
                    "operation": test_cases[i]["operation"],
                }
                resp = await si.si_request_adapter.call(sim, input_dict)
                assert resp["sign"] == expected_results[i]["sign"]
                assert resp["sig"] == expected_results[i]["sig"]
                assert resp["exp"] == expected_results[i]["exp"]
                assert resp["errors"] == expected_results[i]["errors"]

        async def test_process(sim: TestbenchContext):
            await si_test(sim)

        with self.run_simulation(si) as sim:
            sim.add_testbench(test_process)
