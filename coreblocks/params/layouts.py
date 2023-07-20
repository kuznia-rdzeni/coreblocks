from amaranth.utils import *
from coreblocks.params import GenParams, OpType, Funct7, Funct3, Opcode, RegisterType
from coreblocks.params.isa import ExceptionCause
from coreblocks.utils.utils import layout_subset
from coreblocks.utils._typing import LayoutLike, LayoutList

__all__ = [
    "SchedulerLayouts",
    "ROBLayouts",
    "CommonLayouts",
    "FetchLayouts",
    "DecodeLayouts",
    "FuncUnitLayouts",
    "RSInterfaceLayouts",
    "RetirementLayouts",
    "RSLayouts",
    "RFLayouts",
    "UnsignedMulUnitLayouts",
    "RATLayouts",
    "LSULayouts",
    "CSRLayouts",
    "ICacheLayouts",
    "SuperscalarFreeRFLayouts",
    "ExceptionRegisterLayouts",
    "ScoreboardLayouts",
]


class CommonLayouts:
    def __init__(self, gen_params: GenParams):
        self.exec_fn = [
            ("op_type", OpType),
            ("funct3", Funct3),
            ("funct7", Funct7),
        ]
        self.l_register_entry = self.get_reg_description_layout(gen_params.isa.reg_cnt_log)
        self.p_register_entry = self.get_reg_description_layout(gen_params.phys_regs_bits)

        self.regs_l = [
            ("s1", self.l_register_entry),
            ("s2", self.l_register_entry),
            ("dst", self.l_register_entry),
        ]

        self.regs_p = [
            ("s1", self.p_register_entry),
            ("s2", self.p_register_entry),
            ("dst", self.p_register_entry),
        ]

    def get_reg_description_layout(self, width: int):
        reg_desc = [("id", width), ("type", RegisterType)]
        return reg_desc


class SchedulerLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.reg_alloc_in = [
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]
        self.reg_alloc_out = self.renaming_in = [
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("regs_p", [("dst", common.p_register_entry)]),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]
        self.renaming_out = self.rob_allocate_in = [
            ("exec_fn", common.exec_fn),
            (
                "regs_l",
                [
                    ("dst", common.l_register_entry),
                ],
            ),
            ("regs_p", common.regs_p),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]
        self.rob_allocate_out = self.rs_select_in = [
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]
        self.rs_select_out = self.rs_insert_in = [
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("rs_selected", gen_params.rs_number_bits),
            ("rs_entry_id", gen_params.max_rs_entries_bits),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]
        self.free_rf_layout = [("reg_id", gen_params.phys_regs_bits)]


class RFLayouts:
    def __init__(self, gen_params: GenParams):
        self.rf_read_in = self.rf_free = [("reg_id", gen_params.phys_regs_bits)]
        self.rf_read_out = [("reg_val", gen_params.isa.xlen), ("valid", 1)]
        self.rf_write = [("reg_id", gen_params.phys_regs_bits), ("reg_val", gen_params.isa.xlen)]


class RATLayouts:
    def __init__(self, gen_params: GenParams):
        self.set_rename_in = [
            ("rl_dst", gen_params.isa.reg_cnt_log),
            ("rp_dst", gen_params.phys_regs_bits),
        ]
        self.get_rename_in = [
            ("rl_s1", gen_params.isa.reg_cnt_log),
            ("rl_s2", gen_params.isa.reg_cnt_log),
        ]
        self.get_rename_out = [("rp_s1", gen_params.phys_regs_bits), ("rp_s2", gen_params.phys_regs_bits)]

        self.rat_commit_in = [("rl_dst", gen_params.isa.reg_cnt_log), ("rp_dst", gen_params.phys_regs_bits)]
        self.rat_commit_out = [("old_rp_dst", gen_params.phys_regs_bits)]


class SuperscalarFreeRFLayouts:
    def __init__(self, entries_count: int, outputs_count: int):
        self.allocate_in = [
            ("reg_count", bits_for(outputs_count)),
        ]

        self.allocate_out = [(f"reg{i}", log2_int(entries_count, False)) for i in range(outputs_count)]

        self.deallocate_in = [
            ("reg", log2_int(entries_count, False)),
        ]


class ROBLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.data_layout = [
            ("rl_dst", common.l_register_entry),
            ("rp_dst", common.p_register_entry),
        ]

        self.id_layout = [
            ("rob_id", gen_params.rob_entries_bits),
        ]

        self.internal_layout = [
            ("rob_data", self.data_layout),
            ("done", 1),
            ("exception", 1),
            ("block_interrupts", 1),
        ]

        self.mark_done_layout = [
            ("rob_id", gen_params.rob_entries_bits),
            ("exception", 1),
        ]

        self.peek_layout = self.retire_layout = [
            ("rob_data", self.data_layout),
            ("rob_id", gen_params.rob_entries_bits),
            ("exception", 1),
        ]

        self.get_indices = [("start", gen_params.rob_entries_bits), ("end", gen_params.rob_entries_bits)]

        self.block_interrupts = [("rob_id", gen_params.rob_entries_bits)]


class RSInterfaceLayouts:
    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        common = gen_params.get(CommonLayouts)
        self.data_layout: LayoutList = [
            ("rp_s1", common.p_register_entry),
            ("rp_s2", common.p_register_entry),
            ("rp_s1_reg", gen_params.phys_regs_bits),
            ("rp_s2_reg", gen_params.phys_regs_bits),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]

        self.select_out: LayoutLike = [("rs_entry_id", rs_entries_bits)]

        self.insert_in: LayoutLike = [("rs_data", self.data_layout), ("rs_entry_id", rs_entries_bits)]

        self.update_in: LayoutLike = [("tag", common.p_register_entry), ("value", gen_params.isa.xlen)]


class RetirementLayouts:
    def __init__(self, gen_params: GenParams):
        self.precommit = [
            ("rob_id", gen_params.rob_entries_bits),
        ]


class RSLayouts:
    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        rs_interface = gen_params.get(RSInterfaceLayouts, rs_entries_bits=rs_entries_bits)

        self.data_layout: LayoutLike = layout_subset(
            rs_interface.data_layout,
            fields={
                "rp_s1",
                "rp_s2",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "s1_val",
                "s2_val",
                "imm",
                "pc",
            },
        )

        self.insert_in: LayoutLike = [("rs_data", self.data_layout), ("rs_entry_id", rs_entries_bits)]

        self.select_out: LayoutLike = rs_interface.select_out

        self.update_in: LayoutLike = rs_interface.update_in

        self.take_in: LayoutLike = [("rs_entry_id", rs_entries_bits)]

        self.take_out: LayoutLike = layout_subset(
            rs_interface.data_layout,
            fields={
                "s1_val",
                "s2_val",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "imm",
                "pc",
            },
        )

        self.get_ready_list_out: LayoutLike = [("ready_list", 2**rs_entries_bits)]


class ICacheLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue_req = [
            ("addr", gen_params.isa.xlen),
        ]

        self.accept_res = [
            ("instr", gen_params.isa.ilen),
            ("error", 1),
        ]

        self.start_refill = [
            ("addr", gen_params.isa.xlen),
        ]

        self.accept_refill = [
            ("addr", gen_params.isa.xlen),
            ("data", gen_params.isa.xlen),
            ("error", 1),
            ("last", 1),
        ]


class FetchLayouts:
    def __init__(self, gen_params: GenParams):
        self.raw_instr = [
            ("data", gen_params.isa.ilen),
            ("pc", gen_params.isa.xlen),
            ("access_fault", 1),
            ("rvc", 1),
        ]

        self.branch_verify = [
            ("from_pc", gen_params.isa.xlen),
            ("next_pc", gen_params.isa.xlen),
        ]


class DecodeLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        self.decoded_instr = [
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("imm", gen_params.isa.xlen),
            ("imm2", gen_params.imm2_width),
            ("pc", gen_params.isa.xlen),
        ]


class FuncUnitLayouts:
    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)

        self.issue = [
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("rp_dst", common.p_register_entry),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            ("imm", gen_params.isa.xlen),
            ("pc", gen_params.isa.xlen),
        ]

        self.accept = [
            ("rob_id", gen_params.rob_entries_bits),
            ("result", gen_params.isa.xlen),
            ("rp_dst", common.p_register_entry),
            ("exception", 1),
        ]


class UnsignedMulUnitLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue = [
            ("i1", gen_params.isa.xlen),
            ("i2", gen_params.isa.xlen),
        ]

        self.accept = [
            ("o", 2 * gen_params.isa.xlen),
        ]


class DivUnitLayouts:
    def __init__(self, gen: GenParams):
        self.issue = [
            ("dividend", gen.isa.xlen),
            ("divisor", gen.isa.xlen),
        ]

        self.accept = [
            ("quotient", gen.isa.xlen),
            ("remainder", gen.isa.xlen),
        ]


class LSULayouts:
    def __init__(self, gen_params: GenParams):
        self.rs_entries_bits = 0

        rs_interface = gen_params.get(RSInterfaceLayouts, rs_entries_bits=self.rs_entries_bits)
        self.rs_data_layout = layout_subset(
            rs_interface.data_layout,
            fields={
                "rp_s1",
                "rp_s2",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "s1_val",
                "s2_val",
                "imm",
            },
        )

        self.rs_insert_in = [("rs_data", self.rs_data_layout), ("rs_entry_id", self.rs_entries_bits)]

        self.rs_select_out = rs_interface.select_out

        self.rs_update_in = rs_interface.update_in

        retirement = gen_params.get(RetirementLayouts)

        self.precommit = retirement.precommit


class CSRLayouts:
    def __init__(self, gen_params: GenParams):
        self.rs_entries_bits = 0

        self.read = [
            ("data", gen_params.isa.xlen),
            ("read", 1),
            ("written", 1),
        ]

        self.write = [("data", gen_params.isa.xlen)]

        self._fu_read = [("data", gen_params.isa.xlen)]
        self._fu_write = [("data", gen_params.isa.xlen)]

        rs_interface = gen_params.get(RSInterfaceLayouts, rs_entries_bits=self.rs_entries_bits)
        self.rs_data_layout = layout_subset(
            rs_interface.data_layout,
            fields={
                "rp_s1",
                "rp_s1_reg",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "s1_val",
                "imm",
                "imm2",
                "pc",
            },
        )

        self.rs_insert_in = [("rs_data", self.rs_data_layout), ("rs_entry_id", self.rs_entries_bits)]

        self.rs_select_out = rs_interface.select_out

        self.rs_update_in = rs_interface.update_in

        retirement = gen_params.get(RetirementLayouts)

        self.precommit = retirement.precommit


class ExceptionRegisterLayouts:
    def __init__(self, gen_params: GenParams):
        self.get = self.report = [
            ("cause", ExceptionCause),
            ("rob_id", gen_params.rob_entries_bits),
        ]


class ScoreboardLayouts:
    def __init__(self, entries_number: int):
        bits = log2_int(entries_number, False)
        self.set_dirty_in = [("id", bits), ("dirty", 1)]
        self.get_dirty_in = [("id", bits)]
        self.get_dirty_out = [("dirty", 1)]
