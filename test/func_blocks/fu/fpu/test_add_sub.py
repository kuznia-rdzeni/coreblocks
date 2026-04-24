from coreblocks.func_blocks.fu.fpu.fpu_add_sub import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, RoundingModes
from test.func_blocks.fu.fpu.fpu_test_common import FPUTester
from test.func_blocks.fu.fpu.add_sub_test_cases import *
from transactron.testing import *
from amaranth import *
import random
import struct


class TestAddSub(TestCaseWithSimulator):
    def test_manual(self):
        params = FPUParams(sig_width=24, exp_width=8)
        tester = FPUTester(params)
        m = SimpleTestCircuit(FPUAddSubModule(fpu_params=params))

        async def python_float_test(sim: TestbenchContext, request_adapter: TestbenchIO):
            seed = 42
            test_runs = 20
            random.seed(seed)

            for i in range(test_runs):
                input_dict = {}
                p_float_1 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**38))))[0]
                p_float_2 = struct.unpack("f", struct.pack("f", random.uniform(0, 3.4028235 * (10**38))))[0]
                if i < test_runs / 2:
                    input_dict["operation"] = 0
                    result = struct.unpack("f", struct.pack("f", p_float_1 + p_float_2))[0]
                else:
                    input_dict["operation"] = 1
                    result = struct.unpack("f", struct.pack("f", p_float_1 - p_float_2))[0]
                hex_1 = hex(struct.unpack("<I", struct.pack("<f", p_float_1))[0])
                hex_2 = hex(struct.unpack("<I", struct.pack("<f", p_float_2))[0])
                hex_result = hex(struct.unpack("<I", struct.pack("<f", result))[0])

                input_dict["op_1"] = tester.converter.from_hex(hex_1)
                input_dict["op_2"] = tester.converter.from_hex(hex_2)
                input_dict["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN

                result = tester.converter.from_hex(hex_result)
                resp = await request_adapter.call(sim, input_dict)

                assert result["sign"] == resp["sign"]
                assert result["exp"] == resp["exp"]
                assert result["sig"] == resp["sig"]

        async def test_process(sim: TestbenchContext):
            await python_float_test(sim, m.add_sub_request)
            await tester.run_test_set(
                nc_add_rtne,
                nc_add_rtne_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 0},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_add_rtna,
                nc_add_rtna_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_AWAY, "operation": 0},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_add_up,
                nc_add_up_resp,
                {"rounding_mode": RoundingModes.ROUND_UP, "operation": 0},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_add_down,
                nc_add_down_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN, "operation": 0},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_add_zero,
                nc_add_zero_resp,
                {"rounding_mode": RoundingModes.ROUND_ZERO, "operation": 0},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_sub_rtne,
                nc_sub_rtne_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 1},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_sub_rtna,
                nc_sub_rtna_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_AWAY, "operation": 1},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_sub_up,
                nc_sub_up_resp,
                {"rounding_mode": RoundingModes.ROUND_UP, "operation": 1},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_sub_down,
                nc_sub_down_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN, "operation": 1},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                nc_sub_zero,
                nc_sub_zero_resp,
                {"rounding_mode": RoundingModes.ROUND_ZERO, "operation": 1},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                edge_cases_add,
                edge_cases_add_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 0},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                edge_cases_sub,
                edge_cases_sub_resp,
                {"rounding_mode": RoundingModes.ROUND_NEAREST_EVEN, "operation": 1},
                sim,
                m.add_sub_request,
            )

            await tester.run_test_set(
                edge_cases_sub_down,
                edge_cases_sub_down_resp,
                {"rounding_mode": RoundingModes.ROUND_DOWN, "operation": 1},
                sim,
                m.add_sub_request,
            )
            await tester.run_test_set(
                edge_cases_sub_up,
                edge_cases_sub_up_resp,
                {"rounding_mode": RoundingModes.ROUND_UP, "operation": 1},
                sim,
                m.add_sub_request,
            )

        with self.run_simulation(m) as sim:
            sim.add_testbench(test_process)
