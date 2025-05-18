from typing import Optional
from amaranth import signed
from amaranth.lib.data import ArrayLayout
from amaranth.lib.enum import IntFlag, auto
from coreblocks.params import GenParams
from coreblocks.arch import *
from transactron.utils import LayoutList, LayoutListField, layout_subset
from transactron.utils.transactron_helpers import make_layout, extend_layout

__all__ = [
    "CommonLayoutFields",
    "SchedulerLayouts",
    "ROBLayouts",
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
    "CSRRegisterLayouts",
    "CSRUnitLayouts",
    "ICacheLayouts",
    "JumpBranchLayouts",
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

        self.fb_addr: LayoutListField = ("fb_addr", gen_params.isa.xlen - gen_params.fetch_block_bytes_log)
        """Address of a fetch block"""

        self.fb_instr_idx: LayoutListField = ("fb_instr_idx", gen_params.fetch_width_log)
        """Offset of an instruction (counted in number of instructions) in a fetch block"""

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

        self.exec_fn_layout = make_layout(self.op_type, self.funct3, self.funct7)
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

        self.rvc: LayoutListField = ("rvc", 1)
        """Instruction is a compressed (two-byte) one."""

        self.predicted_taken: LayoutListField = ("predicted_taken", 1)
        """If the branch was predicted taken."""

        self.cfi_idx: LayoutListField = ("cfi_idx", gen_params.fetch_width_log)
        """An index of a CFI instruction in a fetch block."""

        self.cfi_target: LayoutListField = ("cfi_target", gen_params.isa.xlen)
        """Target of a CFI instruction."""

        self.cfi_type: LayoutListField = ("cfi_type", CfiType)
        """Type of a CFI instruction"""

        self.branch_mask: LayoutListField = ("branch_mask", gen_params.fetch_width)
        """A mask denoting which instruction in a fetch blocks is a branch."""

        self.tag: LayoutListField = ("tag", gen_params.tag_bits)
        """Instruction tag. Identifies speculation path of the instuction."""

        self.rollback_tag: LayoutListField = ("rollback_tag", gen_params.tag_bits)
        """Target tag of last rollback that happened before instuction.
        For tracking rollbacks in scheduler/CRAT only."""

        self.rollback_tag_v: LayoutListField = ("rollback_tag_v", 1)
        """Valid bit for `rollback_tag`.
        It is set only for first instuction that exits fetch after rollback to `rollback_tag`."""

        self.tag_increment: LayoutListField = ("tag_increment", 1)
        """Compressed tag representation used in ROB.
        Instuction with this bit set has tag of previous instuction incremented by one."""

        self.commit_checkpoint: LayoutListField = ("commit_checkpoint", 1)
        """New checkpoint should be made for this instuction"""


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

        self.reg_alloc_in = self.scheduler_in = make_layout(
            fields.exec_fn,
            fields.regs_l,
            fields.imm,
            fields.csr,
            fields.pc,
            fields.rollback_tag,
            fields.rollback_tag_v,
            fields.commit_checkpoint,
        )

        self.instr_tag_in = self.reg_alloc_out = make_layout(
            fields.exec_fn,
            fields.regs_l,
            self.regs_p_alloc_out,
            fields.imm,
            fields.csr,
            fields.pc,
            fields.rollback_tag,
            fields.rollback_tag_v,
            fields.commit_checkpoint,
        )

        self.renaming_in = self.instr_tag_out = make_layout(
            fields.exec_fn,
            fields.regs_l,
            self.regs_p_alloc_out,
            fields.imm,
            fields.csr,
            fields.pc,
            fields.tag,
            fields.tag_increment,
            fields.commit_checkpoint,
        )

        self.renaming_out = make_layout(
            fields.exec_fn,
            self.regs_l_rob_in,
            fields.regs_p,
            fields.imm,
            fields.csr,
            fields.pc,
            fields.tag,
            fields.tag_increment,
        )

        self.rob_allocate_in = self.renaming_out

        self.rob_allocate_out = make_layout(
            fields.exec_fn,
            fields.regs_p,
            fields.rob_id,
            fields.imm,
            fields.csr,
            fields.pc,
            fields.tag,
        )

        self.rs_select_in = self.rob_allocate_out

        self.rs_select_out = make_layout(
            fields.exec_fn,
            fields.regs_p,
            fields.rob_id,
            self.rs_selected,
            self.rs_entry_id,
            fields.imm,
            fields.csr,
            fields.pc,
            fields.tag,
        )

        self.rs_insert_in = self.rs_select_out

        self.free_rf_layout = make_layout(fields.reg_id)


class RFLayouts:
    """Layouts used in the register file."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.valid: LayoutListField = ("valid", 1)
        """Physical register was assigned a value."""

        self.rf_read_in = make_layout(fields.reg_id)
        self.rf_free = make_layout(fields.reg_id)
        self.rf_read_out = make_layout(fields.reg_val, self.valid)
        self.rf_write = make_layout(fields.reg_id, fields.reg_val)


class RATLayouts:
    """Layouts used in the register alias tables."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.old_rp_dst: LayoutListField = ("old_rp_dst", gen_params.phys_regs_bits)
        """Physical register previously associated with the given logical register in RRAT."""

        self.active_tags_bitmask: LayoutListField = ("active_tags", ArrayLayout(1, 2**gen_params.tag_bits))
        """Bitmask, when bit is set when corresponding tag is on the current speculation/execution
        path and reset when instruction was already rolled back (is not included in current FRAT)"""

        self.frat_rename_in = make_layout(
            fields.rl_s1,
            fields.rl_s2,
            fields.rl_dst,
            fields.rp_dst,
        )
        self.frat_rename_out = make_layout(fields.rp_s1, fields.rp_s2)

        self.rrat_commit_in = make_layout(fields.rl_dst, fields.rp_dst)
        self.rrat_commit_out = make_layout(self.old_rp_dst)

        self.rrat_peek_in = make_layout(fields.rl_dst)
        self.rrat_peek_out = self.rrat_commit_out

        self.rollback_in = make_layout(fields.tag)
        self.get_active_tags_out = make_layout(self.active_tags_bitmask)

        self.crat_rename_in = extend_layout(self.frat_rename_in, fields.tag, fields.commit_checkpoint)
        self.crat_rename_out = self.frat_rename_out

        self.crat_tag_in = (fields.rollback_tag, fields.rollback_tag_v, fields.commit_checkpoint)
        self.crat_tag_out = make_layout(fields.tag, fields.tag_increment, fields.commit_checkpoint)

        self.crat_flush_restore = make_layout(fields.rl_dst, fields.rp_dst)


class ROBLayouts:
    """Layouts used in the reorder buffer."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.data_layout = make_layout(
            fields.rl_dst,
            fields.rp_dst,
            fields.tag_increment,
        )

        self.rob_data: LayoutListField = ("rob_data", self.data_layout)
        """Data stored in a reorder buffer entry."""

        self.done: LayoutListField = ("done", 1)
        """Instruction has executed, but is not committed yet."""

        self.start: LayoutListField = ("start", gen_params.rob_entries_bits)
        """Index of the first (the earliest) entry in the reorder buffer."""

        self.end: LayoutListField = ("end", gen_params.rob_entries_bits)
        """Index of the entry following the last (the latest) entry in the reorder buffer."""

        self.id_layout = make_layout(fields.rob_id)

        self.mark_done_layout = make_layout(
            fields.rob_id,
            fields.exception,
        )

        self.peek_layout = make_layout(
            self.rob_data,
            fields.rob_id,
            fields.exception,
        )

        self.get_indices = make_layout(self.start, self.end)


class RSLayoutFields:
    """Layout fields used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries: int, data_fields: set[str]):
        full_data = gen_params.get(RSFullDataLayout)

        self.data_layout = layout_subset(full_data.data_layout, fields=data_fields)

        self.rs_data: LayoutListField = ("rs_data", self.data_layout)
        """Data about an instuction stored in a reservation station (RS)."""

        self.rs_entry_id: LayoutListField = ("rs_entry_id", range(rs_entries))
        """Index in a reservation station (RS)."""


class RSFullDataLayout:
    """Full data layout for functional blocks. Blocks can use a subset."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.data_layout = make_layout(
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
            fields.tag,
        )


class RSInterfaceLayouts:
    """Layouts used in functional blocks."""

    def __init__(self, gen_params: GenParams, *, rs_entries: int, data_fields: set[str]):
        fields = gen_params.get(CommonLayoutFields)
        rs_fields = gen_params.get(RSLayoutFields, rs_entries=rs_entries, data_fields=data_fields)

        self.data_layout = rs_fields.data_layout

        self.select_out = make_layout(rs_fields.rs_entry_id)

        self.insert_in = make_layout(rs_fields.rs_data, rs_fields.rs_entry_id)

        self.update_in = make_layout(fields.reg_id, fields.reg_val)


class RetirementLayouts:
    """Layouts used in the retirement module."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.precommit_in = make_layout(fields.rob_id)

        self.precommit_out = make_layout(fields.side_fx)

        self.flushing = ("flushing", 1)
        """ Core is currently flushed """

        self.core_state: LayoutList = [self.flushing]


class RSLayouts:
    """Layouts used in the reservation station."""

    def __init__(self, gen_params: GenParams, *, rs_entries: int):
        data_fields = {
            "rp_s1",
            "rp_s2",
            "rp_dst",
            "rob_id",
            "exec_fn",
            "s1_val",
            "s2_val",
            "imm",
            "pc",
            "tag",
        }

        self.rs = gen_params.get(RSInterfaceLayouts, rs_entries=rs_entries, data_fields=data_fields)
        rs_fields = gen_params.get(RSLayoutFields, rs_entries=rs_entries, data_fields=data_fields)

        self.ready_list: LayoutListField = ("ready_list", rs_entries)
        """Bitmask of reservation station entries containing instructions which are ready to run."""

        self.take_in = make_layout(rs_fields.rs_entry_id)

        self.take_out = layout_subset(
            self.rs.data_layout,
            fields={
                "s1_val",
                "s2_val",
                "rp_dst",
                "rob_id",
                "exec_fn",
                "imm",
                "pc",
                "tag",
            },
        )

        self.get_ready_list_out = make_layout(self.ready_list)


class ICacheLayouts:
    """Layouts used in the instruction cache."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.last: LayoutListField = ("last", 1)
        """This is the last cache refill result."""

        self.fetch_block: LayoutListField = ("fetch_block", gen_params.fetch_block_bytes * 8)
        """The block of data the fetch unit operates on."""

        self.issue_req = make_layout(fields.addr)

        self.accept_res = make_layout(
            self.fetch_block,
            fields.error,
        )

        self.start_refill = make_layout(
            fields.addr,
        )

        self.accept_refill = make_layout(
            fields.addr,
            self.fetch_block,
            fields.error,
            self.last,
        )


class FetchLayouts:
    """Layouts used in the fetcher."""

    class AccessFaultFlag(IntFlag):
        # standard access fault when accessing instruction
        # from beginning (exception pc = instruction pc) (fault on full instruction or first half)
        ACCESS_FAULT = auto()
        # with C extension (2-byte alignment enabled) fault condition
        # could only affect second half of 4-byte instruction.
        # Bit set if this is the case
        ACCESS_FAULT_ON_SECOND_HALF = auto()

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.access_fault: LayoutListField = ("access_fault", FetchLayouts.AccessFaultFlag)
        """Instruction fetch errors. See `FetchLayouts.AccessFaultFlag` fields documentation"""

        self.raw_instr = make_layout(
            fields.instr,
            fields.pc,
            self.access_fault,
            fields.rvc,
            fields.predicted_taken,
        )

        self.redirect = make_layout(fields.pc)
        self.resume = make_layout(fields.pc)

        self.predecoded_instr = make_layout(fields.cfi_type, ("cfi_offset", signed(21)), ("unsafe", 1))

        self.bpu_prediction = make_layout(
            fields.branch_mask, fields.cfi_idx, fields.cfi_type, fields.cfi_target, ("cfi_target_valid", 1)
        )

        self.pred_checker_i = make_layout(
            fields.fb_addr,
            ("instr_block_cross", 1),
            ("instr_valid", gen_params.fetch_width),
            ("predecoded", ArrayLayout(self.predecoded_instr, gen_params.fetch_width)),
            ("prediction", self.bpu_prediction),
        )

        self.pred_checker_o = make_layout(
            ("mispredicted", 1),
            ("stall", 1),
            fields.fb_instr_idx,
            ("redirect_target", gen_params.isa.xlen),
        )


class DecodeLayouts:
    """Layouts used in the decoder."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.decoded_instr = make_layout(
            fields.exec_fn,
            fields.regs_l,
            fields.imm,
            fields.csr,
            fields.pc,
        )


class FuncUnitLayouts:
    """Layouts used in functional units."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.result: LayoutListField = ("result", gen_params.isa.xlen)
        """The result value produced in a functional unit."""

        self.issue = make_layout(
            fields.s1_val,
            fields.s2_val,
            fields.rp_dst,
            fields.rob_id,
            fields.exec_fn,
            fields.imm,
            fields.pc,
            fields.tag,
        )

        self.push_result = make_layout(
            fields.rob_id,
            self.result,
            fields.rp_dst,
            fields.exception,
        )


class UnsignedMulUnitLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue = make_layout(
            ("i1", gen_params.isa.xlen),
            ("i2", gen_params.isa.xlen),
        )

        self.accept = make_layout(
            ("o", 2 * gen_params.isa.xlen),
        )


class DivUnitLayouts:
    def __init__(self, gen_params: GenParams):
        self.issue = make_layout(
            ("dividend", gen_params.isa.xlen),
            ("divisor", gen_params.isa.xlen),
        )

        self.accept = make_layout(
            ("quotient", gen_params.isa.xlen),
            ("remainder", gen_params.isa.xlen),
        )


class JumpBranchLayouts:
    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.predicted_jump_target_req = make_layout()
        self.predicted_jump_target_resp = make_layout(fields.cfi_target, ("valid", 1))

        self.verify_branch = make_layout(
            ("from_pc", gen_params.isa.xlen), ("next_pc", gen_params.isa.xlen), ("misprediction", 1)
        )
        """ Hint for Branch Predictor about branch result """

        self.funct7_info = make_layout(
            fields.rvc,
            fields.predicted_taken,
        )
        """Information passed from the frontend to the jumpbranch unit. Encoded in the funct7 field."""


class LSULayouts:
    """Layouts used in the load-store unit."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.store: LayoutListField = ("store", 1)

        self.issue = make_layout(fields.addr, fields.data, fields.funct3, self.store)

        self.issue_out = make_layout(fields.exception, fields.cause)

        self.accept = make_layout(fields.data, fields.exception, fields.cause, fields.addr)


class CSRRegisterLayouts:
    """Layouts used in the control and status registers."""

    def __init__(self, gen_params: GenParams, *, data_width: Optional[int] = None):
        data_width = data_width if data_width is not None else gen_params.isa.xlen

        self.data: LayoutListField = ("data", data_width)

        self.read = make_layout(
            self.data,
            ("read", 1),
            ("written", 1),
        )

        self.write = make_layout(self.data)

        self._fu_read = make_layout(self.data)
        self._fu_write = make_layout(self.data)


class CSRUnitLayouts:
    """Layouts used in the control and status functional unit."""

    def __init__(self, gen_params: GenParams):
        self.rs_entries = 0

        data_fields = {
            "rp_s1",
            "rp_s1_reg",
            "rp_dst",
            "rob_id",
            "exec_fn",
            "s1_val",
            "imm",
            "csr",
            "pc",
            "tag",
        }

        self.rs = gen_params.get(RSInterfaceLayouts, rs_entries=self.rs_entries, data_fields=data_fields)

        self.data_layout = self.rs.data_layout


class ExceptionRegisterLayouts:
    """Layouts used in the exception information register."""

    def __init__(self, gen_params: GenParams):
        fields = gen_params.get(CommonLayoutFields)

        self.mtval: LayoutListField = ("mtval", gen_params.isa.xlen)
        """ Value to set for mtval CSR register """

        self.valid: LayoutListField = ("valid", 1)

        self.report = make_layout(
            fields.cause,
            fields.rob_id,
            fields.pc,
            self.mtval,
        )

        self.get = extend_layout(self.report, self.valid)


class InternalInterruptControllerLayouts:
    def __init__(self, gen_params: GenParams):
        self.cause: LayoutListField = ("cause", gen_params.isa.xlen)
        """ Async interrupt cause code """

        self.interrupt_cause = make_layout(self.cause)


class CoreInstructionCounterLayouts:
    def __init__(self, gen_params: GenParams):
        self.decrement = [("empty", 1)]
