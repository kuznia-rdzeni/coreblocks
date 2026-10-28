edge_cases_mul = [
    # +inf * -inf
    [0x7F800000, 0xFF800000],
    # +inf * 0
    [0x7F800000, 0x80000000],
    # qNaN * number
    [0x7FC00000, 0x7F400000],
    # qNaN * sNaN
    [0x7FC00000, 0x7FA00001],
    # result is subnormal
    [0x3F800001, 0x00000001],
    # norm * sub = norm
    [0x7F000000, 0x00400000],
    # overflow
    [0x7F000000, 0x7F000000],
    # subnormals underflow to zero
    [0x80000FAC, 0x037E7F60],
    # Round Nearest Even edge cases
    [0xC07FFFEE, 0x4FFF0010],
    [0xC00007EF, 0x3DFFF7BF],
    # Round Nearest Away edge cases
    [0x4131F471, 0x387C7FA2],
    [0x7E8000FB, 0xBE9FFFFB],
    # RPI edge cases
    [0xBFFFFFEE, 0xCEFFC006],
    [0x40FFFFBF, 0x4403FFFF],
    # RNI edge cases
    [0xBE8D8ACA, 0xBF7FFF3E],
    [0x5F770000, 0xDDF5C7C2],
    # Round Zero edge cases
    [0xC1E20853, 0x3D801003],
    [0x3D0CF32D, 0xC17FBFBF],
]
