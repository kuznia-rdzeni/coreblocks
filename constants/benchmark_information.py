ecp5 = [
    {
        "name": "Max clock frequency (Fmax)",
        "unit": "MHz",
        "value": 0,
        "regex": "(\\d+\\.\\d\\d) MHz",
        "keyword": "Max frequency for clock",
    },
    {"name": "Device utilisation: (ECP5)", "unit": "LUT4", "value": 0, "regex": "(\\d+)/\\d+", "keyword": "logic LUTs"},
    {"name": "LUTs used as carry: (ECP5)", "unit": "LUT", "value": 0, "regex": "(\\d+)/\\d+", "keyword": "carry LUTs"},
    {"name": "LUTs used as ram: (ECP5)", "unit": "LUT", "value": 0, "regex": "(\\d+)/\\d+", "keyword": "RAM LUTs"},
    {"name": "LUTs used as DFF: (ECP5)", "unit": "LUT", "value": 0, "regex": "(\\d+)/\\d+", "keyword": "Total DFFs"},
]
