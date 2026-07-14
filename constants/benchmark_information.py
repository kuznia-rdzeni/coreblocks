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
xc7a200t = [
    {
        "name": "Max clock frequency (Fmax)",
        "unit": "MHz",
        "value": 0,
        "regex": "(\\d+\\.\\d\\d) MHz",
        "keyword": "Max frequency for clock",
    },
    {"name": "LUT used", "unit": "LUT", "value": 0, "regex": "(\\d+)/ *\\d+", "keyword": "SLICE_LUTX"},
    {"name": "LUT DFF used", "unit": "LUT", "value": 0, "regex": "(\\d+)/ *\\d+", "keyword": "SLICE_FFX"},
    {"name": "Slice carry chains used", "unit": "Slice", "value": 0, "regex": "(\\d+)/ *\\d+", "keyword": "CARRY4"},
    {
        "name": "Block RAM used",
        "unit": "RAMB36E1",
        "value": 0,
        "regex": "(\\d+)/ *\\d+",
        "keyword": ["RAMB18E1", "RAMB36E1", "FIFO18E1", "RAMBFIFO36E1"],
        "update": lambda kw, old, new: old + new / 2 if kw == "RAMB18E1" else old + new,
    },
]
