from coreblocks.func_blocks.fu.fpu.fpu_add_sub import *
from coreblocks.func_blocks.fu.fpu.fpu_common import FPUParams, FPUCommonValues, RoundingModes
from transactron import TModule
from transactron.lib import AdapterTrans
from transactron.testing import *
from amaranth import *

# ADD
# 7F21FFFF 3CBB907D 7F21FFFF 01
# FF80013F FFFFFFFF FFFFFFFF 10
# 3F7F0040 BFFFFFFF BF807FDF 00
# SUB
# C00007EF 3DFFF7BF C00807AD 01
# 8683F7FF C07F3FFF 407F3FFF 01
# E6FFFFFE B3FFFFFF E6FFFFFE 01


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
            "is_inf": ((exp == self.cv.max_exp) & (sig == 0)),
            "is_nan": ((exp == self.cv.max_exp) & (sig != 0)),
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
        converter = ToFloatConverter(params)
        add_sub = TestAddSub.AddSubModuleTest(params)

        def compare_results(lhs, rhs):
            assert lhs["sign"] == rhs["sign"]
            assert lhs["exp"] == rhs["exp"]
            assert lhs["sig"] == rhs["sig"]

        def print_test_case_debug(t_case, num):
            print(f"test_case {num}")
            print("op_1")
            print(f"sign: {t_case["op_1"]["sign"]}")
            print("exp: {:08b}".format(t_case["op_1"]["exp"]))
            print("sig: {:024b}".format(t_case["op_1"]["sig"]))
            # print(f"is_nan: {t_case["op_1"]["is_nan"]}")
            print("op_2")
            print(f"sign: {t_case["op_2"]["sign"]}")
            print("exp: {:08b}".format(t_case["op_2"]["exp"]))
            print("sig: {:024b}".format(t_case["op_2"]["sig"]))
            # print(f"is_nan: {t_case["op_2"]["is_nan"]}")

        def print_response_debug(resp, num):
            print(f"response: {num}")
            print(f"sign: {resp["sign"]}")
            print("exp: {:08b}".format(resp["exp"]))
            print("sig: {:024b}".format(resp["sig"]))
            print(f"exceptions: {resp["errors"]}")

        async def nc_add_rnte(sim: TestbenchContext):
            test_cases = [
                {
                    "op_1": converter.from_hex("7F21FFFF"),
                    "op_2": converter.from_hex("3CBB907D"),
                },
                {
                    "op_1": converter.from_hex("FF80013F"),
                    "op_2": converter.from_hex("FFFFFFFF"),
                },
                {
                    "op_1": converter.from_hex("3F7F0040"),
                    "op_2": converter.from_hex("BFFFFFFF"),
                },
            ]
            result_number = [
                converter.from_hex("7F21FFFF"),
                converter.from_hex("7FC00000"),
                converter.from_hex("BF807FDF"),
            ]

            result_exceptions = [
                int("01", 16),
                int("10", 16),
                int("00", 16),
            ]

            for num, t_case in enumerate(test_cases):
                t_case["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN
                t_case["operation"] = 0
                # print_test_case_debug(t_case,num)
                resp = await add_sub.add_sub_request_adapter.call(sim, t_case)
                # print_response_debug(resp,num)
                compare_results(resp, result_number[num])
                assert resp["errors"] == result_exceptions[num]

        async def nc_sub_rnte(sim: TestbenchContext):
            test_cases = [
                {
                    "op_1": converter.from_hex("C00007EF"),
                    "op_2": converter.from_hex("3DFFF7BF"),
                },
                {
                    "op_1": converter.from_hex("8683F7FF"),
                    "op_2": converter.from_hex("C07F3FFF"),
                },
                {
                    "op_1": converter.from_hex("E6FFFFFE"),
                    "op_2": converter.from_hex("B3FFFFFF"),
                },
                # E6FFFFFE B3FFFFFF E6FFFFFE 01
            ]
            result_number = [
                converter.from_hex("C00807AD"),
                converter.from_hex("407F3FFF"),
                converter.from_hex("E6FFFFFE"),
            ]

            result_exceptions = [
                int("01", 16),
                int("01", 16),
                int("01", 16),
            ]

            for num, t_case in enumerate(test_cases):
                t_case["rounding_mode"] = RoundingModes.ROUND_NEAREST_EVEN
                t_case["operation"] = 1
                # print_test_case_debug(t_case,num)
                resp = await add_sub.add_sub_request_adapter.call(sim, t_case)
                # print_response_debug(resp,num)
                compare_results(resp, result_number[num])
                assert resp["errors"] == result_exceptions[num]

        async def corner_cases(sim: TestbenchContext):
            assert 2 == 4

        async def test_process(sim: TestbenchContext):
            await nc_add_rnte(sim)
            await nc_sub_rnte(sim)
            await corner_cases(sim)

        with self.run_simulation(add_sub) as sim:
            sim.add_testbench(test_process)
