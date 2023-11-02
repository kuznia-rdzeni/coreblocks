from coreblocks.params import GenParams, OpType, Funct7, Funct3
from coreblocks.params.isa import ExceptionCause
from coreblocks.utils.utils import layout_subset
from coreblocks.utils import LayoutList

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
        
        self.exec_fn = ("exec_fn", [self.op_type, self.funct3, self.funct7])
        """Decoded instruction."""

        self.regs_l = ("regs_l", [self.rl_s1, self.rl_s2, self.rl_dst])
        """Logical register numbers - as described in the RISC V manual. They index the RATs."""
        
        self.regs_p = ("regs_p", [self.rp_s1, self.rp_s2, self.rp_dst])
        """Physical register numbers. They index the register file."""


class SchedulerLayouts:
    """Layouts used in the scheduler."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

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
            ("regs_p", [fields.rp_dst]),
            fields.imm,
            fields.csr,
            fields.pc,
        ]

        self.renaming_out = self.rob_allocate_in = [
            fields.exec_fn,
            (
                "regs_l",
                [
                    fields.rl_dst,
                    ("rl_dst_v", 1),
                ],
            ),
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
    """Layouts used in the register alias tables."""

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


class RSLayoutFields:
    """Layout fields used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries_bits: int, data_layout: LayoutList):
        self.rs_data = ("rs_data", data_layout)
        self.rs_entry_id = ("rs_entry_id", rs_entries_bits)


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
        rs_fields = gen_params.get(RSLayoutFields, rs_entries_bits=rs_entries_bits, data_layout=data_layout)

        self.data_layout = data_layout

        self.select_out = [rs_fields.rs_entry_id]

        self.insert_in = [rs_fields.rs_data, rs_fields.rs_entry_id]

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

        self.take_in = [("rs_entry_id", rs_entries_bits)]

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
