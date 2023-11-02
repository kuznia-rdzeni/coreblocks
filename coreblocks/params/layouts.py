from coreblocks.params import GenParams, OpType, Funct7, Funct3
from coreblocks.params.isa import ExceptionCause
from coreblocks.utils.utils import layout_subset

__all__ = [
    "SchedulerLayouts",
    "ROBLayouts",
    "CommonLayouts",
    "FetchLayouts",
    "DecodeLayouts",
    "FuncUnitLayouts",
    "RSInterfaceLayouts",
    "RSLayouts",
    "RFLayouts",
    "UnsignedMulUnitLayouts",
    "RATLayouts",
    "LSULayouts",
    "CSRLayouts",
    "ICacheLayouts",
]


class CommonLayoutFields:
    """Commonly used layout fields."""

    def __init__(self, gen_params: GenParams):
        self.op_type = ("op_type", OpType)
        """Decoded operation type."""

        self.funct3 = ("funct3", Funct3)
        """RISC V funct3 value."""

        self.funct7 = ("funct7", Funct7)
        """RISC V funct7 value."""

        self.rl_s1 = ("rl_s1", gen_params.isa.reg_cnt_log)
        """Logical register number of first source operand."""

        self.rl_s2 = ("rl_s2", gen_params.isa.reg_cnt_log)
        """Logical register number of second source operand."""

        self.rl_dst = ("rl_dst", gen_params.isa.reg_cnt_log)
        """Logical register number of destination operand."""

        self.rp_s1 = ("rp_s1", gen_params.phys_regs_bits)
        """Physical register number of first source operand."""

        self.rp_s2 = ("rp_s2", gen_params.phys_regs_bits)
        """Physical register number of second source operand."""

        self.rp_dst = ("rp_dst", gen_params.phys_regs_bits)
        """Physical register number of destination operand."""

        self.imm = ("imm", gen_params.isa.xlen)
        """Immediate value."""

        self.csr = ("csr", gen_params.isa.csr_alen)
        """CSR number."""

        self.pc = ("pc", gen_params.isa.xlen)
        """Program counter value."""

        self.rob_id = ("rob_id", gen_params.rob_entries_bits)
        """Reorder buffer entry identifier."""

        self.s1_val = ("s1_val", gen_params.isa.xlen)
        """Value of first source operand."""

        self.s2_val = ("s2_val", gen_params.isa.xlen)
        """Value of second source operand."""

        self.addr = ("addr", gen_params.isa.xlen)
        """Memory address."""

        self.data = ("data", gen_params.isa.xlen)
        """Piece of data."""

        self.instr = ("instr", gen_params.isa.ilen)
        """RISC V instruction."""


class CommonLayouts:
    """Commonly used layouts."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.exec_fn = [
            fields.op_type,
            fields.funct3,
            fields.funct7,
        ]
        """Decoded instructions."""

        self.regs_l = [
            fields.rl_s1,
            fields.rl_s2,
            fields.rl_dst,
        ]
        """Logical register numbers - as described in the RISC V manual. They index the RATs."""

        self.regs_p = [
            fields.rp_dst,
            fields.rp_s1,
            fields.rp_s2,
        ]
        """Physical register numbers. They index the register file."""


class SchedulerLayouts:
    """Layouts used in the scheduler."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)
        common = gen_params.get(CommonLayouts)

        self.reg_alloc_in = [
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.reg_alloc_out = self.renaming_in = [
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            ("regs_p", [("rp_dst", gen_params.phys_regs_bits)]),
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.renaming_out = self.rob_allocate_in = [
            ("exec_fn", common.exec_fn),
            (
                "regs_l",
                [
                    ("rl_dst", gen_params.isa.reg_cnt_log),
                    ("rl_dst_v", 1),
                ],
            ),
            ("regs_p", common.regs_p),
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rob_allocate_out = self.rs_select_in = [
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rs_select_out = self.rs_insert_in = [
            ("exec_fn", common.exec_fn),
            ("regs_p", common.regs_p),
            ("rob_id", gen_params.rob_entries_bits),
            ("rs_selected", gen_params.rs_number_bits),
            ("rs_entry_id", gen_params.max_rs_entries_bits),
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.free_rf_layout = [("reg_id", gen_params.phys_regs_bits)]


class RFLayouts:
    """Layouts used in the register file."""

    def __init__(self, gen_params: GenParams):
        self.rf_read_in = self.rf_free = [("reg_id", gen_params.phys_regs_bits)]
        self.rf_read_out = [("reg_val", gen_params.isa.xlen), ("valid", 1)]
        self.rf_write = [("reg_id", gen_params.phys_regs_bits), ("reg_val", gen_params.isa.xlen)]


class RATLayouts:
    """Layouts usef in the register alias tables."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.rat_rename_in = [
            fields.rl_s1,
            fields.rl_s2,
            fields.rl_dst,
            fields.rp_dst,
        ]

        self.rat_rename_out = [fields.rp_s1, fields.rp_s2]

        self.rat_commit_in = [fields.rl_dst, fields.rp_dst]

        self.rat_commit_out = [("old_rp_dst", gen_params.phys_regs_bits)]


class ROBLayouts:
    """Layouts used in the reorder buffer."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.data_layout = [
            fields.rl_dst,
            fields.rp_dst,
        ]

        self.id_layout = [
            fields.rob_id
        ]

        self.internal_layout = [
            ("rob_data", self.data_layout),
            ("done", 1),
            ("exception", 1),
        ]

        self.mark_done_layout = [
            fields.rob_id,
            ("exception", 1),
        ]

        self.peek_layout = self.retire_layout = [
            ("rob_data", self.data_layout),
            fields.rob_id,
            ("exception", 1),
        ]

        self.get_indices = [("start", gen_params.rob_entries_bits), ("end", gen_params.rob_entries_bits)]


class RSInterfaceLayouts:
    """Layouts used in functional blocks."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        fields = gen_params.get(CommonLayoutFields)
        common = gen_params.get(CommonLayouts)

        self.data_layout = [
            fields.rp_s1,
            fields.rp_s2,
            ("rp_s1_reg", gen_params.phys_regs_bits),
            ("rp_s2_reg", gen_params.phys_regs_bits),
            fields.rp_dst,
            fields.rob_id,
            ("exec_fn", common.exec_fn),
            fields.s1_val,
            fields.s2_val,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.select_out = [("rs_entry_id", rs_entries_bits)]

        self.insert_in = [("rs_data", self.data_layout), ("rs_entry_id", rs_entries_bits)]

        self.update_in = [("tag", gen_params.phys_regs_bits), ("value", gen_params.isa.xlen)]


class RetirementLayouts:
    """Layouts used in the retirement module."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.precommit = [
            fields.rob_id
        ]


class RSLayouts:
    """Layouts used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        rs_interface = gen_params.get(RSInterfaceLayouts, rs_entries_bits=rs_entries_bits)

        self.data_layout = layout_subset(
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

        self.insert_in = [("rs_data", self.data_layout), ("rs_entry_id", rs_entries_bits)]

        self.select_out = rs_interface.select_out

        self.update_in = rs_interface.update_in

        self.take_in = [("rs_entry_id", rs_entries_bits)]

        self.take_out = layout_subset(
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

        self.get_ready_list_out = [("ready_list", 2**rs_entries_bits)]


class ICacheLayouts:
    """Layouts used in the instruction cache."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.issue_req = [
            fields.addr
        ]

        self.accept_res = [
            fields.instr,
            ("error", 1),
        ]

        self.start_refill = [
            fields.addr,
        ]

        self.accept_refill = [
            fields.addr,
            fields.data,
            ("error", 1),
            ("last", 1),
        ]


class FetchLayouts:
    """Layouts used in the fetcher."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.raw_instr = [
            fields.instr,
            fields.pc,
            ("access_fault", 1),
            ("rvc", 1),
        ]

        self.branch_verify = [
            ("from_pc", gen_params.isa.xlen),
            ("next_pc", gen_params.isa.xlen),
        ]


class DecodeLayouts:
    """Layouts used in the decoder."""

    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        fields = gen_params.get(CommonLayoutFields)

        self.decoded_instr = [
            ("exec_fn", common.exec_fn),
            ("regs_l", common.regs_l),
            fields.imm,
            fields.csr,
            fields.pc,
        ]


class FuncUnitLayouts:
    """Layouts used in functional units."""

    def __init__(self, gen_params: GenParams):
        common = gen_params.get(CommonLayouts)
        fields = gen_params.get(CommonLayoutFields)

        self.issue = [
            ("s1_val", gen_params.isa.xlen),
            ("s2_val", gen_params.isa.xlen),
            ("rp_dst", gen_params.phys_regs_bits),
            ("rob_id", gen_params.rob_entries_bits),
            ("exec_fn", common.exec_fn),
            fields.imm,
            fields.pc,
        ]

        self.accept = [
            fields.rob_id,
            ("result", gen_params.isa.xlen),
            fields.rp_dst,
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
    """Layouts used in the load-store unit."""

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
    """Layouts used in the control and status registers."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.rs_entries_bits = 0

        self.read = [
            ("data", gen_params.isa.xlen),
            ("read", 1),
            ("written", 1),
        ]

        self.write = [fields.data]

        self._fu_read = [fields.data]
        self._fu_write = [fields.data]

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
                "csr",
                "pc",
            },
        )

        self.rs_insert_in = [("rs_data", self.rs_data_layout), ("rs_entry_id", self.rs_entries_bits)]

        self.rs_select_out = rs_interface.select_out

        self.rs_update_in = rs_interface.update_in

        retirement = gen_params.get(RetirementLayouts)

        self.precommit = retirement.precommit


class ExceptionRegisterLayouts:
    """Layouts used in the exception register."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.get = self.report = [
            ("cause", ExceptionCause),
            fields.rob_id,
        ]
