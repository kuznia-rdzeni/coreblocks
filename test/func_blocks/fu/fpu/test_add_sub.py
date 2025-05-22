from coreblocks.func_blocks.fu.fpu.fpu_add_sub import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, FPUCommonValues, RoundingModes
from test.func_blocks.fu.fpu.add_sub_test_cases import *
from transactron import TModule
from transactron.lib import AdapterTrans
from transactron.testing import *
from amaranth import *


class FPUTester:
    def __init__(self, params: FPUParams):
        self.params = params
        self.converter = ToFloatConverter(params)

    def __compare_results__(self, lhs, rhs):
        assert lhs["sign"] == rhs["sign"]
        assert lhs["exp"] == rhs["exp"]
        assert lhs["sig"] == rhs["sig"]

    async def run_test_set(self, cases, result, common_input, sim: TestbenchContext, request_adapter: AdapterTrans):
        assert len(cases) == len(result)
        for num, case in enumerate(cases):
            input_dict = {}
            for key, value in common_input.items():
                input_dict[key] = value
            input_dict["op_1"] = self.converter.from_hex(case[0])
            input_dict["op_2"] = self.converter.from_hex(case[1])
            resp = await request_adapter.call(sim, input_dict)
            self.__compare_results__(resp, self.converter.from_hex(result[num][0]))

            assert resp["errors"] == int(result[num][1], 16)


class ToFloatConverter:
    def __init__(self, params: FPUParams):
        self.params = params
        self.all_width = self.params.sig_width - 1 + self.params.exp_width + 1
        self.sig_width = self.params.sig_width - 1
        self.exp_mask = (2**self.params.exp_width) - 1
        self.sig_mask = (2 ** (self.params.sig_width - 1)) - 1
        self.implicit_one = 1 << (self.params.sig_width - 1)
        self.cv = FPUCommonValues(self.params)

    def from_hex(self, hex_float):
        number = int(hex_float, 16)
        exp = (number >> self.sig_width) & self.exp_mask
        sig = number & self.sig_mask
        if exp != 0:
            sig = sig | self.implicit_one
        return {
            "sign": number >> (self.all_width - 1),
            "exp": exp,
            "sig": sig,
            "is_inf": ((exp == self.cv.max_exp) & ((sig & (~self.implicit_one)) == 0)),
            "is_nan": ((exp == self.cv.max_exp) & ((sig & (~self.implicit_one)) != 0)),
            "is_zero": ((exp == 0) & (sig == 0)),
        }


class TestAddSub(TestCaseWithSimulator):
    class AddSubModuleTest(Elaboratable):
        def __init__(self, params: FPUParams):
            self.params = params

        def elaborate(self, platform):
            m = TModule()
            m.submodules.add_sub_module = add_sub_module = self.add_sub_module = FPUAddSubModule(fpu_params=self.params)
            m.submodules.request = self.add_sub_request_adapter = TestbenchIO(
                AdapterTrans(add_sub_module.add_sub_request)
            )
            return m

    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        tester = FPUTester(params)
        add_sub = TestAddSub.AddSubModuleTest(params)

        async def corner_cases(sim: TestbenchContext):
            assert 2 == 4

        async def test_process(sim: TestbenchContext):
            await tester.run_test_set(
                nc_add_rtne,
                nc_add_rtne_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 0},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_add_rtna,
                nc_add_rtna_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_AWAY, "operation": 0},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_add_up,
                nc_add_up_resp,
                {"rounding_mode": RoundingModes.ROUND_UP, "operation": 0},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_add_down,
                nc_add_down_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN, "operation": 0},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_add_zero,
                nc_add_zero_resp,
                {"rounding_mode": RoundingModes.ROUND_ZERO, "operation": 0},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_sub_rtne,
                nc_sub_rtne_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_sub_rtna,
                nc_sub_rtna_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_AWAY, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_sub_up,
                nc_sub_up_resp,
                {"rounding_mode": RoundingModes.ROUND_UP, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_sub_down,
                nc_sub_down_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                nc_sub_zero,
                nc_sub_zero_resp,
                {"rounding_mode": RoundingModes.ROUND_ZERO, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                edge_cases_add,
                edge_cases_add_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 0},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                edge_cases_sub,
                edge_cases_sub_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

            await tester.run_test_set(
                edge_cases_sub_down,
                edge_cases_sub_down_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )
            await tester.run_test_set(
                edge_cases_sub_up,
                edge_cases_sub_up_resp,
                {"rounding_mode": RoundingModes.ROUND_UP, "operation": 1},
                sim,
                add_sub.add_sub_request_adapter,
            )

        with self.run_simulation(add_sub) as sim:
            sim.add_testbench(test_process)
