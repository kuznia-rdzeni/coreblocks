edge_cases_mul = [
    # +inf * -inf
    ["7F800000", "FF800000"],
    # +inf * 0
    ["7F800000", "80000000"],
    # qNaN * number
    ["7FC00000", "7F400000"],
    # qNaN * sNaN
    ["7FC00000", "7FA00001"],
    # result is subnormal
    ["3F800001", "00000001"],
    # norm * sub = norm
    ["7F000000", "00400000"],
    # overflow
    ["7F000000", "7F000000"],
]

edge_cases_mul_resp = [
    ["7F800000", "00"],
    ["7FC00000", "10"],
    ["7FC00000", "00"],
    ["7FC00000", "10"],
    ["00000001", "03"],
    ["3F800000", "00"],
    ["7F800000", "05"],
]

rne_cases_mul = [
    ["C07FFFEE", "4FFF0010"],
    ["C00007EF", "3DFFF7BF"],
]

rne_cases_mul_resp = [
    ["D0FEFFFE", "01"],
    ["BE8003CE", "01"],
]

rna_cases_mul = [
    ["4131F471", "387C7FA2"],
    ["7E8000FB", "BE9FFFFB"],
]

rna_cases_mul_resp = [
    ["3A2F8558", "01"],
    ["FDA00135", "01"],
]

rpi_cases_mul = [
    ["BFFFFFEE", "CEFFC006"],
    ["40FFFFBF", "4403FFFF"],
]

rpi_cases_mul_resp = [
    ["4F7FBFF5", "01"],
    ["4583FFDE", "01"],
]

rni_cases_mul = [
    ["BE8D8ACA", "BF7FFF3E"],
    ["5F770000", "DDF5C7C2"],
]

rni_cases_mul_resp = [
    ["3E8D8A5E", "01"],
    ["FDED23BD", "01"],
]

rz_cases_mul = [
    ["C1E20853", "3D801003"],
    ["3D0CF32D", "C17FBFBF"],
]

rz_cases_mul_resp = [
    ["BFE22499", "01"],
    ["BF0CCFCC", "01"],
]
