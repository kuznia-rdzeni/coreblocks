import random
from coreblocks.func_blocks.fu.fpu.lza import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams
from transactron import TModule
from transactron.lib import AdapterTrans
from transactron.testing import *
from amaranth import *


def clz(sig_a, sig_b, carry, sig_width):
    zeros = 0
    msb_bit_mask = 1 << (sig_width - 1)
    sum = sig_a + sig_b + carry
    while 1:
        if not (sum & msb_bit_mask):
            zeros += 1
            sum = sum << 1
        else:
            return zeros


class TestLZA(TestCaseWithSimulator):
    class LZAModuleTest(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.lza = lza = self.lza_module = LZAModule(fpu_params=self.params)
            m.submodules.predict = self.predict_request_adapter = TestbenchIO(AdapterTrans(lza.predict_request))
            return m

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        lza = TestLZA.LZAModuleTest(params)

        async def random_test(sim: TestbenchContext, seed: int, iters: int):
            xor_mask = (2**params.sig_width) - 1
            random.seed(seed)
            for _ in range(iters):
                sig_a = random.randint(1 << (params.sig_width - 1), (2**params.sig_width) - 1)
                sig_b = random.randint(1 << (params.sig_width - 1), sig_a)
                sig_b = (sig_b ^ xor_mask) | (1 << params.sig_width)
                resp = await lza.predict_request_adapter.call(sim, {"sig_a": sig_a, "sig_b": sig_b, "carry": 0})
                pred_lz = resp["shift_amount"]
                true_lz = clz(sig_a, sig_b, 0, params.sig_width)
                assert pred_lz == true_lz or (pred_lz + 1) == true_lz

        async def lza_edge_cases_test(sim: TestbenchContext):
            test_cases = [
                {
                    "sig_a": 0b111110001010110011001111,
                    "sig_b": 0b000001110101001100110000,
                    "carry": 0,
                },
                {
                    "sig_a": 0b111110001010110011001111,
                    "sig_b": 0b000001110101001100110000,
                    "carry": 1,
                },
                {
                    "sig_a": 0b111111111111111111111111,
                    "sig_b": 0b000000000000000000000001,
                    "carry": 0,
                },
                {
                    "sig_a": 0b101110111101111011011101,
                    "sig_b": 0b001000000000000000000001,
                    "carry": 1,
                },
            ]
            expected_results = [
                {"shift_amount": 23, "is_zero": 0},
                {"shift_amount": 24, "is_zero": 1},
                {"shift_amount": 24, "is_zero": 0},
                {"shift_amount": 0, "is_zero": 0},
            ]
            for i in range(len(test_cases)):
                resp = await lza.predict_request_adapter.call(sim, test_cases[i])
                assert resp["shift_amount"] == expected_results[i]["shift_amount"]
                assert resp["is_zero"] == expected_results[i]["is_zero"]

        async def test_process(sim: TestbenchContext):
            await lza_edge_cases_test(sim)
            await random_test(sim, 2024, 20)

        with self.run_simulation(lza) as sim:
            sim.add_testbench(test_process)
