from coreblocks.func_blocks.fu.fpu.fpu_common import IEEE754_F32
from test.func_blocks.fu.fpu.float_generator import FloatGenerator
from test.func_blocks.fu.fpu.fpu_test_common import FloatData


gen = FloatGenerator(IEEE754_F32)

edge_cases_add = [
    [gen.plus.inf, FloatData(0, 0xFE, 0x400)],
    [gen.minus.inf, FloatData(0, 0xFE, 0x400)],
    [gen.plus.zero, FloatData(1, 0x1, 0x80000)],
    [gen.plus.subnormal(0x200000), FloatData(0, 0x1, 0x400000)],
    [gen.plus.subnormal(0x200000), gen.plus.subnormal(0x180001)],
    [FloatData(0, 0x1, 0x3), FloatData(1, 0x1, 0x3)],
]

nc_add_rtne = [
    [FloatData(0, 0xFE, 0x21FFFF), FloatData(0, 0x79, 0x3B907D)],
    [gen.minus.snan(0x13F), gen.minus.qnan(0x3FFFFF)],
    [FloatData(0, 0x7E, 0x7F0040), FloatData(1, 0x7F, 0x7FFFFF)],
]

nc_add_rtna = [
    [gen.minus.qnan(0x3FFFFE), FloatData(1, 0x7F, 0x7FFFFF)],
    [gen.plus.subnormal(0x32C625), FloatData(1, 0x1, 0x600004)],
    [FloatData(0, 0x7F, 0x7FFF1E), FloatData(0, 0x9E, 0x801)],
]

nc_add_zero = [
    [FloatData(0, 0x7E, 0x5EE18F), FloatData(1, 0x7B, 0x6FFFFB)],
    [FloatData(0, 0x7D, 0x3DFFFF), FloatData(1, 0x75, 0xC0000)],
    [FloatData(1, 0x7D, 0x2C4A43), FloatData(1, 0x7E, 0x7FFFFE)],
]

nc_add_up = [
    [FloatData(1, 0x80, 0x7FFFEE), FloatData(0, 0x9F, 0x7F0010)],
    [gen.minus.qnan(0x3FFFFE), gen.minus.snan(0x1)],
    [FloatData(0, 0xFD, 0x7FBFF), FloatData(0, 0x7F, 0x8939E)],
]

nc_add_down = [
    [FloatData(1, 0x7F, 0x7FA), FloatData(1, 0x1B, 0x71952E)],
    [FloatData(0, 0xE1, 0x83), FloatData(0, 0x9D, 0x3FFFF7)],
    [FloatData(0, 0xBD, 0x3FFFA), FloatData(1, 0x80, 0xFE)],
]

nc_sub_rtne = [
    [FloatData(1, 0x80, 0x7EF), FloatData(0, 0x7B, 0x7FF7BF)],
    [FloatData(1, 0xD, 0x3F7FF), FloatData(1, 0x80, 0x7F3FFF)],
    [FloatData(1, 0xCD, 0x7FFFFE), FloatData(1, 0x67, 0x7FFFFF)],
]

nc_sub_rtna = [
    [FloatData(0, 0x9E, 0x200FF), FloatData(1, 0xBD, 0x80FE)],
    [FloatData(0, 0x83, 0x5D4434), gen.minus.inf],
    [FloatData(0, 0x7D, 0x7FFFFE), FloatData(1, 0x83, 0x7FFFC4)],
]

nc_sub_zero = [
    [FloatData(1, 0xBD, 0x20000E), FloatData(0, 0x83, 0x7F8003)],
    [FloatData(1, 0x7E, 0x7BBFFF), FloatData(0, 0x67, 0x7FFFDD)],
    [gen.minus.qnan(0x3FFFFE), FloatData(0, 0xFE, 0x3FFF7)],
]

nc_sub_up = [
    [FloatData(1, 0x7F, 0x7FEFFE), FloatData(0, 0xFE, 0x7FE1FF)],
    [FloatData(0, 0x7F, 0x7FF008), FloatData(0, 0x7E, 0x7FF0)],
    [FloatData(1, 0x86, 0x7FF7DE), FloatData(0, 0x9C, 0x7EC37)],
]

nc_sub_down = [
    [FloatData(0, 0x90, 0x803FF), FloatData(0, 0x82, 0x30000)],
    [FloatData(0, 0xBF, 0x7), FloatData(1, 0xBE, 0x7FE080)],
    [FloatData(1, 0xB9, 0x101FFF), FloatData(0, 0xFE, 0x7FFFFE)],
]

add_sub_edge_cases = (
    edge_cases_add
    + nc_add_rtne
    + nc_add_rtna
    + nc_add_zero
    + nc_add_up
    + nc_add_down
    + nc_sub_rtne
    + nc_sub_rtna
    + nc_sub_zero
    + nc_sub_up
    + nc_sub_down
)
