from coreblocks.func_blocks.fu.fpu.fpu_common import FPUCommonValues, FPUParams
from transactron.testing import *


class FPUTester:
    def __init__(self, params: FPUParams):
        self.params = params
        self.converter = ToFloatConverter(params)

    def __compare_results__(self, lhs, rhs):
        assert lhs["sign"] == rhs["sign"]
        assert lhs["exp"] == rhs["exp"]
        assert lhs["sig"] == rhs["sig"]

    async def run_test_set(self, cases, result, common_input, sim: TestbenchContext, request_adapter: TestbenchIO):
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
