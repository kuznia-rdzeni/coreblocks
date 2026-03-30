from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.zbkx import ZbkxFunction, ZbkxComponent

from test.func_blocks.fu.functional_common import ExecFn, FunctionalUnitTestCase


class TestZbkxUnit(FunctionalUnitTestCase[ZbkxFunction.Fn]):
    func_unit = ZbkxComponent()
    zero_imm = False

    ops = {
        ZbkxFunction.Fn.XPERM4: ExecFn(OpType.CROSSBAR_PERMUTATION, Funct3.XPERM4, Funct7.XPERM),
        ZbkxFunction.Fn.XPERM8: ExecFn(OpType.CROSSBAR_PERMUTATION, Funct3.XPERM8, Funct7.XPERM),
    }

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: ZbkxFunction.Fn, xlen: int) -> dict[str, int]:
        result = 0

        match fn:
            case ZbkxFunction.Fn.XPERM4:
                lane_count = xlen // 4
                for lane in range(lane_count):
                    idx = (i2 >> (lane * 4)) & 0xF
                    nibble = ((i1 >> (idx * 4)) & 0xF) if idx < lane_count else 0
                    result |= nibble << (lane * 4)

            case ZbkxFunction.Fn.XPERM8:
                lane_count = xlen // 8
                for lane in range(lane_count):
                    idx = (i2 >> (lane * 8)) & 0xFF
                    byte = ((i1 >> (idx * 8)) & 0xFF) if idx < lane_count else 0
                    result |= byte << (lane * 8)

        return {"result": result & ((1 << xlen) - 1)}

    def test_fu(self):
        self.run_standard_fu_test()
