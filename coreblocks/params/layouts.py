from coreblocks.params import GenParams, OpType, Funct7, Funct3
from coreblocks.params.isa import ExceptionCause
from transactron.utils.utils import layout_subset
from transactron.utils import LayoutList, LayoutListField

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

        self.reg_val: LayoutListField = ("reg_val", gen_params.isa.xlen)
        """Value of some physical register."""

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

        self.cause: LayoutListField = ("cause", ExceptionCause)
        """Exception cause."""

        self.error: LayoutListField = ("error", 1)
        """Request ended with an error."""

        self.side_fx: LayoutListField = ("side_fx", 1)
        """Side effects are enabled."""


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

        self.regs_l_rob_in: LayoutListField = (
            "regs_l",
            [
                fields.rl_dst,
                ("rl_dst_v", 1),
            ],
        )
        """Logical register number for the destination operand, before ROB allocation."""

        self.reg_alloc_in: LayoutList = [
            fields.exec_fn,
            fields.regs_l,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.reg_alloc_out: LayoutList = [
            fields.exec_fn,
            fields.regs_l,
            self.regs_p_alloc_out,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.renaming_in = self.reg_alloc_out

        self.renaming_out: LayoutList = [
            fields.exec_fn,
            self.regs_l_rob_in,
            fields.regs_p,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rob_allocate_in = self.renaming_out

        self.rob_allocate_out: LayoutList = [
            fields.exec_fn,
            fields.regs_p,
            fields.rob_id,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rs_select_in = self.rob_allocate_out

        self.rs_select_out: LayoutList = [
            fields.exec_fn,
            fields.regs_p,
            fields.rob_id,
            self.rs_selected,
            self.rs_entry_id,
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.rs_insert_in = self.rs_select_out

        self.free_rf_layout: LayoutList = [fields.reg_id]


class RFLayouts:
    """Layouts used in the register file."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.valid: LayoutListField = ("valid", 1)
        """Physical register was assigned a value."""

        self.rf_read_in: LayoutList = [fields.reg_id]
        self.rf_free: LayoutList = [fields.reg_id]
        self.rf_read_out: LayoutList = [fields.reg_val, self.valid]
        self.rf_write: LayoutList = [fields.reg_id, fields.reg_val]


class RATLayouts:
    """Layouts used in the register alias tables."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.old_rp_dst: LayoutListField = ("old_rp_dst", gen_params.phys_regs_bits)
        """Physical register previously associated with the given logical register in RRAT."""

        self.rat_rename_in: LayoutList = [
            fields.rl_s1,
            fields.rl_s2,
            fields.rl_dst,
            fields.rp_dst,
        ]

        self.rat_rename_out: LayoutList = [fields.rp_s1, fields.rp_s2]

        self.rat_commit_in: LayoutList = [fields.rl_dst, fields.rp_dst, fields.side_fx]

        self.rat_commit_out: LayoutList = [self.old_rp_dst]


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

        self.data_layout: LayoutList = [
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

        self.data_layout: LayoutList = data_layout

        self.select_out: LayoutList = [rs_fields.rs_entry_id]

        self.insert_in: LayoutList = [rs_fields.rs_data, rs_fields.rs_entry_id]

        self.update_in: LayoutList = [fields.reg_id, fields.reg_val]


class RetirementLayouts:
    """Layouts used in the retirement module."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.precommit: LayoutList = [fields.rob_id, fields.side_fx]


class RSLayouts:
    """Layouts used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int):
        data = gen_params.get(RSFullDataLayout)

        self.ready_list: LayoutListField = ("ready_list", 2**rs_entries_bits)
        """Bitmask of reservation station entries containing instructions which are ready to run."""

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

        self.take_in: LayoutList = [rs_fields.rs_entry_id]

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

        self.get_ready_list_out: LayoutList = [self.ready_list]


class ICacheLayouts:
    """Layouts used in the instruction cache."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.error: LayoutListField = ("last", 1)
        """This is the last cache refill result."""

        self.issue_req: LayoutList = [fields.addr]

        self.accept_res: LayoutList = [
            fields.instr,
            fields.error,
        ]

        self.start_refill: LayoutList = [
            fields.addr,
        ]

        self.accept_refill: LayoutList = [
            fields.addr,
            fields.data,
            fields.error,
            self.error,
        ]


class FetchLayouts:
    """Layouts used in the fetcher."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.access_fault: LayoutListField = ("access_fault", 1)
        """Instruction fetch failed."""

        self.rvc: LayoutListField = ("rvc", 1)
        """Instruction is a compressed (two-byte) one."""

        self.raw_instr: LayoutList = [
            fields.instr,
            fields.pc,
            self.access_fault,
            self.rvc,
        ]

        self.branch_verify: LayoutList = [
            ("from_pc", gen_params.isa.xlen),
            ("next_pc", gen_params.isa.xlen),
        ]


class DecodeLayouts:
    """Layouts used in the decoder."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.decoded_instr: LayoutList = [
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

        self.issue: LayoutList = [
            fields.s1_val,
            fields.s2_val,
            fields.rp_dst,
            fields.rob_id,
            fields.exec_fn,
            fields.imm,
            fields.pc,
        ]

        self.accept: LayoutList = [
            fields.rob_id,
            self.result,
            fields.rp_dst,
            fields.exception,
        ]


class UnsignedMulUnitLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue: LayoutList = [
            ("i1", gen_params.isa.xlen),
            ("i2", gen_params.isa.xlen),
        ]

        self.accept: LayoutList = [
            ("o", 2 * gen_params.isa.xlen),
        ]


class DivUnitLayouts:
    def __init__(self, gen: GenParams):
        self.issue: LayoutList = [
            ("dividend", gen.isa.xlen),
            ("divisor", gen.isa.xlen),
        ]

        self.accept: LayoutList = [
            ("quotient", gen.isa.xlen),
            ("remainder", gen.isa.xlen),
        ]


class LSULayouts:
    """Layouts used in the load-store unit."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)
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

        self.store: LayoutListField = ("store", 1)

        self.issue: LayoutList = [fields.addr, fields.data, fields.funct3, self.store]

        self.issue_out: LayoutList = [fields.exception, fields.cause]

        self.accept: LayoutList = [fields.data, fields.exception, fields.cause]


class CSRLayouts:
    """Layouts used in the control and status registers."""

    def __init__(self, gen_params: GenParams):
        data = gen_params.get(RSFullDataLayout)
        fields = gen_params.get(CommonLayoutFields)

        self.rs_entries_bits = 0

        self.read: LayoutList = [
            fields.data,
            ("read", 1),
            ("written", 1),
        ]

        self.write: LayoutList = [fields.data]

        self._fu_read: LayoutList = [fields.data]
        self._fu_write: LayoutList = [fields.data]

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

        self.get: LayoutList = [
            fields.cause,
            fields.rob_id,
        ]

        self.report = self.get
