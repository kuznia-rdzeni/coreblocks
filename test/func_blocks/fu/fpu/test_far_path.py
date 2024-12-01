from coreblocks.func_blocks.fu.fpu.far_path import *
from coreblocks.func_blocks.fu.fpu.fpu_common import (
    RoundingModes,
    FPUParams,
)
from transactron import TModule
from transactron.lib import AdapterTrans
from parameterized import parameterized
from transactron.testing import *
from amaranth import *


class TestFarPath(TestCaseWithSimulator):
    class FarPathModule(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.fp = fp = self.far_path = FarPathModule(fpu_params=self.params)
            m.submodules.compute = self.far_path_request_adapter = TestbenchIO(AdapterTrans(fp.far_path_request))
            return m


    params = FPUParams(sig_width=24, exp_width=8)


    def test_far_path_addition(self):
        params = FPUParams(sig_width=24, exp_width=8)
        far_path = TestFarPath.FarPathModule(params)
        async def test_ORS(sim:TestbenchContext):
            test_cases = [
                #one right_shift 000000000000000000000000
                {
                    "r_sign": 0,
                    "sig_a": 0b111110000000000000000001,
                    "sig_b": 0b000010000000000000000000,
                    "exp": 10,
                    "sub_op": 0,
                    "rounding_mode": RoundingModes.ROUND_UP,
                    "guard_bit":0,
                    "round_bit":1,
                    "sticky_bit":0,
                }
                ]
            expected_results = [
                {
                    "out_exp":11,
                    "out_sig":0b100000000000000000000000,
                    "output_round":1,
                    "output_sticky":1,
                }
                ]
            for i in range(len(test_cases)):
                resp = await far_path.far_path_request_adapter.call(sim,input_dict[i])
                assert resp.out_exp == expected_results[i]["out_exp"] 
                assert resp.out_sig == expected_results[i]["out_sig"] 
                assert resp.output_round == expected_results[i]["output_round"] 
                assert resp.output_sticky == expected_results[i]["output_sticky"] 

        async def test_process(sim:TestbenchContext):
            await test_ORS(sim)

        with self.run_simulation(fpurt) as sim:
            sim.add_testbench(test_process)
