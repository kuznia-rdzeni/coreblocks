from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32
from test.func_blocks.fu.fpu.float_generator import FloatGenerator
from test.func_blocks.fu.fpu.fpu_test_common import FloatData


gen = FloatGenerator(IEEE754_F32)

edge_cases_mul = [
    # qNaN * number
    [gen.plus.qnan(0), FloatData(0, 0xFE, 0x400000)],
    # qNaN * sNaN
    [gen.plus.qnan(0), gen.plus.snan(1)],
    # result is subnormal
    [FloatData(0, 0x7F, 0x1), gen.plus.subnormal(1)],
    # norm * sub = norm
    [FloatData(0, 0xFE, 0x0), gen.plus.subnormal(0x400000)],
    # overflow
    [FloatData(0, 0xFE, 0x0), FloatData(0, 0xFE, 0x0)],
    # underflow to zero
    [gen.minus.subnormal(0xFAC), FloatData(0, 0x6, 0x7E7F60)],
    # Round Nearest Even edge cases
    [FloatData(1, 0x80, 0x7FFFEE), FloatData(0, 0x9F, 0x7F0010)],
    [FloatData(1, 0x80, 0x7EF), FloatData(0, 0x7B, 0x7FF7BF)],
    # Round Nearest Away edge cases
    [FloatData(0, 0x82, 0x31F471), FloatData(0, 0x70, 0x7C7FA2)],
    [FloatData(0, 0xFD, 0xFB), FloatData(1, 0x7D, 0x1FFFFB)],
    # RPI edge cases
    [FloatData(1, 0x7F, 0x7FFFEE), FloatData(1, 0x9D, 0x7FC006)],
    [FloatData(0, 0x81, 0x7FFFBF), FloatData(0, 0x88, 0x3FFFF)],
    # RNI edge cases
    [FloatData(1, 0x7D, 0xD8ACA), FloatData(1, 0x7E, 0x7FFF3E)],
    [FloatData(0, 0xBE, 0x770000), FloatData(1, 0xBB, 0x75C7C2)],
    # Round Zero edge cases
    [FloatData(1, 0x83, 0x620853), FloatData(0, 0x7B, 0x1003)],
    [FloatData(0, 0x7A, 0xCF32D), FloatData(1, 0x82, 0x7FBFBF)],
]
