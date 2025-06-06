edge_cases_add = [
    ["7F800000", "FF800000"],
    ["7FC00000", "7f800008"],
    ["7F800000", "7FC00000"],
    ["7F800000", "7F000400"],
    ["FF800000", "7F000400"],
    ["00000000", "80880000"],
    ["00000000", "00000000"],
    ["FF7FFFFF", "FF7FFFFF"],
    ["00200000", "00C00000"],
    ["00200000", "00180001"],
    ["00800003", "80800003"],
    ["80000000", "80000000"],
]

edge_cases_add_resp = [
    ["7FC00000", "10"],
    ["7FC00000", "10"],
    ["7FC00000", "00"],
    ["7F800000", "00"],
    ["FF800000", "00"],
    ["80880000", "00"],
    ["00000000", "00"],
    ["FF800000", "05"],
    ["00E00000", "00"],
    ["00380001", "00"],
    ["00000000", "00"],
    ["80000000", "00"],
]

edge_cases_sub_down = [["00800000", "00800000"], ["00000000", "80000000"]]
edge_cases_sub_down_resp = [["80000000", "00"], ["00000000", "00"]]

edge_cases_sub_up = [["00800000", "00800000"], ["80000000", "00000000"]]
edge_cases_sub_up_resp = [["00000000", "00"], ["80000000", "00"]]

edge_cases_sub = [["7F800000", "7F800000"]]
edge_cases_sub_resp = [["7FC00000", "10"]]

nc_add_rtne = [
    [
        "7F21FFFF",
        "3CBB907D",
    ],
    ["FF80013F", "FFFFFFFF"],
    [
        "3F7F0040",
        "BFFFFFFF",
    ],
]
nc_add_rtne_resp = [["7F21FFFF", "01"], ["7FC00000", "10"], ["BF807FDF", "00"]]

nc_add_rtna = [["FFFFFFFE", "BFFFFFFF"], ["0032C625", "80E00004"], ["3FFFFF1E", "4F000801"]]
nc_add_rtna_resp = [["7FC00000", "00"], ["80AD39DF", "00"], ["4F000801", "01"]]

nc_add_zero = [["3F5EE18F", "BDEFFFFB"], ["3EBDFFFF", "BA8C0000"], ["BEAC4A43", "BF7FFFFE"]]
nc_add_zero_resp = [["3F40E18F", "01"], ["3EBD73FF", "00"], ["BFAB128F", "01"]]

nc_add_up = [["C07FFFEE", "4FFF0010"], ["FFFFFFFE", "FF800001"], ["7E87FBFF", "3F88939E"]]
nc_add_up_resp = [["4FFF0010", "01"], ["7FC00000", "10"], ["7E87FC00", "01"]]

nc_add_down = [["BF8007FA", "8DF1952E"], ["70800083", "4EBFFFF7"], ["5E83FFFA", "C00000FE"]]
nc_add_down_resp = [["BF8007FB", "01"], ["70800083", "01"], ["5E83FFF9", "01"]]

nc_sub_rtne = [
    [
        "C00007EF",
        "3DFFF7BF",
    ],
    [
        "8683F7FF",
        "C07F3FFF",
    ],
    [
        "E6FFFFFE",
        "B3FFFFFF",
    ],
]
nc_sub_rtne_resp = [["C00807AD", "01"], ["407F3FFF", "01"], ["E6FFFFFE", "01"]]

nc_sub_rtna = [["4F0200FF", "DE8080FE"], ["41DD4434", "FF800000"], ["3EFFFFFE", "C1FFFFC4"]]
nc_sub_rtna_resp = [["5E8080FE", "01"], ["7F800000", "00"], ["4201FFE2", "01"]]

nc_sub_zero = [["DEA0000E", "41FF8003"], ["BF7BBFFF", "33FFFFDD"], ["FFFFFFFE", "7F03FFF7"]]
nc_sub_zero_resp = [["DEA0000E", "01"], ["BF7BC000", "01"], ["7FC00000", "00"]]

nc_sub_up = [["BFFFEFFE", "7F7FE1FF"], ["3FFFF008", "3F007FF0"], ["C37FF7DE", "4E07EC37"]]
nc_sub_up_resp = [["FF7FE1FF", "01"], ["3FBFB010", "00"], ["CE07EC3A", "01"]]

nc_sub_down = [["480803FF", "41030000"], ["5F800007", "DF7FE080"], ["DC901FFF", "7F7FFFFE"]]
nc_sub_down_resp = [["480801F3", "00"], ["5FFFF047", "00"], ["FF7FFFFF", "01"]]
