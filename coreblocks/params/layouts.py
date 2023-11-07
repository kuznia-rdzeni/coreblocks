from coreblocks.params import GenParams, OpType, Funct7, Funct3
from coreblocks.params.isa import ExceptionCause
from coreblocks.utils.utils import layout_subset
from coreblocks.utils import LayoutList, LayoutListField

__all__ = [
    "CommonLayoutFields",
    "SchedulerLayouts",
    "ROBLayouts",
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
        self.op_type: LayoutListField = ("op_type", OpType)
        """Decoded operation type."""

        self.funct3: LayoutListField = ("funct3", Funct3)
        """RISC V funct3 value."""

        self.funct7: LayoutListField = ("funct7", Funct7)
        """RISC V funct7 value."""

        self.rl_s1: LayoutListField = ("rl_s1", gen_params.isa.reg_cnt_log)
        """Logical register number of first source operand."""

        self.rl_s2: LayoutListField = ("rl_s2", gen_params.isa.reg_cnt_log)
        """Logical register number of second source operand."""

        self.rl_dst: LayoutListField = ("rl_dst", gen_params.isa.reg_cnt_log)
        """Logical register number of destination operand."""

        self.rp_s1: LayoutListField = ("rp_s1", gen_params.phys_regs_bits)
        """Physical register number of first source operand."""

        self.rp_s2: LayoutListField = ("rp_s2", gen_params.phys_regs_bits)
        """Physical register number of second source operand."""

        self.rp_dst: LayoutListField = ("rp_dst", gen_params.phys_regs_bits)
        """Physical register number of destination operand."""

        self.imm: LayoutListField = ("imm", gen_params.isa.xlen)
        """Immediate value."""

        self.csr: LayoutListField = ("csr", gen_params.isa.csr_alen)
        """CSR number."""

        self.pc: LayoutListField = ("pc", gen_params.isa.xlen)
        """Program counter value."""

        self.rob_id: LayoutListField = ("rob_id", gen_params.rob_entries_bits)
        """Reorder buffer entry identifier."""

        self.s1_val: LayoutListField = ("s1_val", gen_params.isa.xlen)
        """Value of first source operand."""

        self.s2_val: LayoutListField = ("s2_val", gen_params.isa.xlen)
        """Value of second source operand."""

        self.addr: LayoutListField = ("addr", gen_params.isa.xlen)
        """Memory address."""

        self.data: LayoutListField = ("data", gen_params.isa.xlen)
        """Piece of data."""

        self.instr: LayoutListField = ("instr", gen_params.isa.ilen)
        """RISC V instruction."""

        self.exec_fn_layout: LayoutList = [self.op_type, self.funct3, self.funct7]
        """Decoded instruction, in layout form."""

        self.exec_fn: LayoutListField = ("exec_fn", self.exec_fn_layout)
        """Decoded instruction."""

        self.regs_l: LayoutListField = ("regs_l", [self.rl_s1, self.rl_s2, self.rl_dst])
        """Logical register numbers - as described in the RISC V manual. They index the RATs."""

        self.regs_p: LayoutListField = ("regs_p", [self.rp_s1, self.rp_s2, self.rp_dst])
        """Physical register numbers. They index the register file."""

        self.reg_id: LayoutListField = ("reg_id", gen_params.phys_regs_bits)
        """Physical register ID."""

        self.exception: LayoutListField = ("exception", 1)
        """Exception is raised for this instruction."""


class SchedulerLayouts:
    """Layouts used in the scheduler."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.rs_selected: LayoutListField = ("rs_selected", gen_params.rs_number_bits)
        """Reservation Station number for the instruction."""

        self.rs_entry_id: LayoutListField = ("rs_entry_id", gen_params.max_rs_entries_bits)
        """Reservation station entry ID for the instruction."""

        self.regs_p_alloc_out: LayoutListField = ("regs_p", [fields.rp_dst])
        """Physical register number for the destination operand, after allocation."""

        self.regs_l_rob_in = (
            "regs_l",
            [
                fields.rl_dst,
                ("rl_dst_v", 1),
            ],
        )
        """Logical register number for the destination operand, before ROB allocation."""

        self.reg_alloc_in = [
            fields.exec_fn,
            fields.regs_l,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.reg_alloc_out = self.renaming_in = [
            fields.exec_fn,
            fields.regs_l,
            self.regs_p_alloc_out,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.renaming_out = self.rob_allocate_in = [
            fields.exec_fn,
            self.regs_l_rob_in,
            fields.regs_p,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rob_allocate_out = self.rs_select_in = [
            fields.exec_fn,
            fields.regs_p,
            fields.rob_id,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rs_select_out = self.rs_insert_in = [
            fields.exec_fn,
            fields.regs_p,
            fields.rob_id,
            self.rs_selected,
            self.rs_entry_id,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.free_rf_layout = [fields.reg_id]


class RFLayouts:
    """Layouts used in the register file."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.valid: LayoutListField = ("valid", 1)
        """Physical register was assigned a value."""

        self.rf_read_in = self.rf_free = [fields.reg_id]
        self.rf_read_out = [("reg_val", gen_params.isa.xlen), self.valid]
        self.rf_write = [fields.reg_id, ("reg_val", gen_params.isa.xlen)]


class RATLayouts:
    """Layouts used in the register alias tables."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.old_rp_dst: LayoutListField = ("old_rp_dst", gen_params.phys_regs_bits)
        """Physical register previously associated with the given logical register in RRAT."""

        self.rat_rename_in = [
            fields.rl_s1,
            fields.rl_s2,
            fields.rl_dst,
            fields.rp_dst,
        ]

        self.rat_rename_out = [fields.rp_s1, fields.rp_s2]

        self.rat_commit_in = [fields.rl_dst, fields.rp_dst]

        self.rat_commit_out = [self.old_rp_dst]


class ROBLayouts:
    """Layouts used in the reorder buffer."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.data_layout: LayoutList = [
            fields.rl_dst,
            fields.rp_dst,
        ]

        self.rob_data: LayoutListField = ("rob_data", self.data_layout)
        """Data stored in a reorder buffer entry."""

        self.done: LayoutListField = ("done", 1)
        """Instruction has executed, but is not committed yet."""

        self.start: LayoutListField = ("start", gen_params.rob_entries_bits)
        """Index of the first (the earliest) entry in the reorder buffer."""

        self.end: LayoutListField = ("end", gen_params.rob_entries_bits)
        """Index of the entry following the last (the latest) entry in the reorder buffer."""

        self.id_layout: LayoutList = [fields.rob_id]

        self.internal_layout: LayoutList = [
            self.rob_data,
            self.done,
            fields.exception,
        ]

        self.mark_done_layout: LayoutList = [
            fields.rob_id,
            fields.exception,
        ]

        self.peek_layout: LayoutList = [
            self.rob_data,
            fields.rob_id,
            fields.exception,
        ]

        self.retire_layout: LayoutList = self.peek_layout

        self.get_indices: LayoutList = [self.start, self.end]


class RSLayoutFields:
    """Layout fields used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int, data_layout: LayoutList):
        self.rs_data: LayoutListField = ("rs_data", data_layout)
        """Data about an instuction stored in a reservation station (RS)."""

        self.rs_entry_id: LayoutListField = ("rs_entry_id", rs_entries_bits)
        """Index in a reservation station (RS)."""


class RSFullDataLayout:
    """Full data layout for functional blocks. Blocks can use a subset."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.data_layout = [
            fields.rp_s1,
            fields.rp_s2,
            ("rp_s1_reg", gen_params.phys_regs_bits),
            ("rp_s2_reg", gen_params.phys_regs_bits),
            fields.rp_dst,
            fields.rob_id,
            fields.exec_fn,
            fields.s1_val,
            fields.s2_val,
            fields.imm,
            fields.csr,
            fields.pc,
        ]


class RSInterfaceLayouts:
    """Layouts used in functional blocks."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int, data_layout: LayoutList):
        fields = gen_params.get(CommonLayoutFields)
        rs_fields = gen_params.get(RSLayoutFields, rs_entries_bits=rs_entries_bits, data_layout=data_layout)

        self.data_layout = data_layout

        self.select_out = [rs_fields.rs_entry_id]

        self.insert_in = [rs_fields.rs_data, rs_fields.rs_entry_id]

        self.update_in = [("tag", gen_params.phys_regs_bits), fields.data]


class RetirementLayouts:
    """Layouts used in the retirement module."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.precommit = [fields.rob_id]


class RSLayouts:
    """Layouts used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        data = gen_params.get(RSFullDataLayout)

        data_layout = layout_subset(
            data.data_layout,
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

        self.rs = gen_params.get(RSInterfaceLayouts, rs_entries_bits=rs_entries_bits, data_layout=data_layout)
        rs_fields = gen_params.get(RSLayoutFields, rs_entries_bits=rs_entries_bits, data_layout=data_layout)

        self.take_in = [rs_fields.rs_entry_id]

        self.take_out = layout_subset(
            data.data_layout,
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

        self.issue_req = [fields.addr]

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

        self.access_fault: LayoutListField = ("access_fault", 1)
        """Bit flag, says that instruction fetch failed."""

        self.rvc: LayoutListField = ("rvc", 1)
        """Bit flag, says that an instruction is a compressed (two-byte) one."""

        self.raw_instr = [
            fields.instr,
            fields.pc,
            self.access_fault,
            self.rvc,
        ]

        self.branch_verify = [
            ("from_pc", gen_params.isa.xlen),
            ("next_pc", gen_params.isa.xlen),
        ]


class DecodeLayouts:
    """Layouts used in the decoder."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.decoded_instr = [
            fields.exec_fn,
            fields.regs_l,
            fields.imm,
            fields.csr,
            fields.pc,
        ]


class FuncUnitLayouts:
    """Layouts used in functional units."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.result: LayoutListField = ("result", gen_params.isa.xlen)
        """The result value produced in a functional unit."""

        self.issue = [
            fields.s1_val,
            fields.s2_val,
            fields.rp_dst,
            fields.rob_id,
            fields.exec_fn,
            fields.imm,
            fields.pc,
        ]

        self.accept = [
            fields.rob_id,
            self.result,
            fields.rp_dst,
            fields.exception,
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
        data = gen_params.get(RSFullDataLayout)

        data_layout = layout_subset(
            data.data_layout,
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

        self.rs_entries_bits = 0

        self.rs = gen_params.get(RSInterfaceLayouts, rs_entries_bits=self.rs_entries_bits, data_layout=data_layout)

        retirement = gen_params.get(RetirementLayouts)

        self.precommit = retirement.precommit


class CSRLayouts:
    """Layouts used in the control and status registers."""

    def __init__(self, gen_params: GenParams):
        data = gen_params.get(RSFullDataLayout)
        fields = gen_params.get(CommonLayoutFields)

        self.rs_entries_bits = 0

        self.read = [
            fields.data,
            ("read", 1),
            ("written", 1),
        ]

        self.write = [fields.data]

        self._fu_read = [fields.data]
        self._fu_write = [fields.data]

        data_layout = layout_subset(
            data.data_layout,
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

        self.rs = gen_params.get(RSInterfaceLayouts, rs_entries_bits=self.rs_entries_bits, data_layout=data_layout)

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
