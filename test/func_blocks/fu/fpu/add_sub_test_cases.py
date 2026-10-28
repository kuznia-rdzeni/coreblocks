edge_cases_add = [
    # +inf + -inf
    [0x7F800000, 0xFF800000],
    # nan + snan
    [0x7FC00000, 0x7F800008],
    # +inf + nan
    [0x7F800000, 0x7FC00000],
    [0x7F800000, 0x7F000400],
    [0xFF800000, 0x7F000400],
    [0x00000000, 0x80880000],
    # 0 + 0
    [0x00000000, 0x00000000],
    [0xFF7FFFFF, 0xFF7FFFFF],
    [0x00200000, 0x00C00000],
    [0x00200000, 0x00180001],
    [0x00800003, 0x80800003],
    # -0 + -0
    [0x80000000, 0x80000000],
]

edge_cases_sub_down = [[0x00800000, 0x00800000], [0x00000000, 0x80000000]]

edge_cases_sub_up = [[0x00800000, 0x00800000], [0x80000000, 0x00000000]]

edge_cases_sub = [[0x7F800000, 0x7F800000]]

nc_add_rtne = [
    [
        0x7F21FFFF,
        0x3CBB907D,
    ],
    [0xFF80013F, 0xFFFFFFFF],
    [
        0x3F7F0040,
        0xBFFFFFFF,
    ],
]

nc_add_rtna = [[0xFFFFFFFE, 0xBFFFFFFF], [0x0032C625, 0x80E00004], [0x3FFFFF1E, 0x4F000801]]

nc_add_zero = [[0x3F5EE18F, 0xBDEFFFFB], [0x3EBDFFFF, 0xBA8C0000], [0xBEAC4A43, 0xBF7FFFFE]]

nc_add_up = [[0xC07FFFEE, 0x4FFF0010], [0xFFFFFFFE, 0xFF800001], [0x7E87FBFF, 0x3F88939E]]

nc_add_down = [[0xBF8007FA, 0x8DF1952E], [0x70800083, 0x4EBFFFF7], [0x5E83FFFA, 0xC00000FE]]

nc_sub_rtne = [
    [
        0xC00007EF,
        0x3DFFF7BF,
    ],
    [
        0x8683F7FF,
        0xC07F3FFF,
    ],
    [
        0xE6FFFFFE,
        0xB3FFFFFF,
    ],
]

nc_sub_rtna = [[0x4F0200FF, 0xDE8080FE], [0x41DD4434, 0xFF800000], [0x3EFFFFFE, 0xC1FFFFC4]]

nc_sub_zero = [[0xDEA0000E, 0x41FF8003], [0xBF7BBFFF, 0x33FFFFDD], [0xFFFFFFFE, 0x7F03FFF7]]

nc_sub_up = [[0xBFFFEFFE, 0x7F7FE1FF], [0x3FFFF008, 0x3F007FF0], [0xC37FF7DE, 0x4E07EC37]]

nc_sub_down = [[0x480803FF, 0x41030000], [0x5F800007, 0xDF7FE080], [0xDC901FFF, 0x7F7FFFFE]]

add_sub_edge_cases = (
    edge_cases_add
    + edge_cases_sub_down
    + edge_cases_sub_up
    + edge_cases_sub
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
