from collections.abc import Sequence

from amaranth import *

from transactron import Method, Transaction, TModule
from transactron.lib import FIFO
from coreblocks.interface.layouts import SchedulerLayouts
from coreblocks.params import GenParams
from coreblocks.arch.optypes import OpType
from transactron.lib.connectors import Connect
from transactron.utils import assign, AssignType
from transactron.utils.dependencies import DependencyContext
from coreblocks.interface.keys import CoreStateKey
from coreblocks.func_blocks.interface.func_protocols import FuncBlock


__all__ = ["Scheduler"]


class RegAllocation(Elaboratable):
    """
    Module performing the "Register allocation" step (allocating a physical register for
    the instruction result). A part of the scheduling process.
    """

    def __init__(self, *, get_instr: Method, push_instr: Method, get_free_reg: Method, gen_params: GenParams):
        """
        Parameters
        ----------
        get_instr: Method
            Method providing decoded instructions to be scheduled for execution. Uses
            `SchedulerLayouts.reg_alloc_in`.
        push_instr: Method
            Method used for pushing the serviced instruction to the next step. Uses `SchedulerLayouts.reg_alloc_out`.
        get_free_reg: Method
             Method providing the ID of a currently free physical register.
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.reg_alloc_in
        self.output_layout = layouts.reg_alloc_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.get_free_reg = get_free_reg

    def elaborate(self, platform):
        m = TModule()

        free_reg = Signal(self.gen_params.phys_regs_bits)
        data_out = Signal(self.output_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)
            with m.If(instr.regs_l.rl_dst != 0):
                reg_id = self.get_free_reg(m)
                m.d.comb += free_reg.eq(reg_id)

            m.d.comb += assign(data_out, instr)
            m.d.comb += data_out.regs_p.rp_dst.eq(free_reg)
            self.push_instr(m, data_out)

        return m


class Renaming(Elaboratable):
    """
    Module performing the "Renaming source register" (translation from logical register
    name to physical register name) step of the scheduling process. Additionally it updates
    the F-RAT with the translation from the logical destination register ID to the physical ID.
    """

    def __init__(self, *, get_instr: Method, push_instr: Method, rename: Method, gen_params: GenParams):
        """
        Parameters
        ----------
        get_instr: Method
            Method providing instructions with an allocated physical register. Uses `SchedulerLayouts.renaming_in`.
        push_instr: Method
            Method used for pushing the serviced instruction to the next step. Uses `SchedulerLayouts.renaming_out`.
        rename: Method
            Method used for renaming the source register in F-RAT. Uses
            `RATLayouts.rename_input_layout` and `RATLayouts.rename_output_layout`.
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.renaming_in
        self.output_layout = layouts.renaming_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rename = rename

    def elaborate(self, platform):
        m = TModule()

        data_out = Signal(self.output_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)
            renamed_regs = self.rename(
                m,
                rl_s1=instr.regs_l.rl_s1,
                rl_s2=instr.regs_l.rl_s2,
                rl_dst=instr.regs_l.rl_dst,
                rp_dst=instr.regs_p.rp_dst,
            )

            m.d.comb += assign(data_out, instr, fields={"exec_fn", "imm", "csr", "pc", "ftq_addr"})
            m.d.comb += assign(data_out.regs_l, instr.regs_l, fields=AssignType.COMMON)
            m.d.comb += data_out.regs_p.rp_dst.eq(instr.regs_p.rp_dst)
            m.d.comb += data_out.regs_p.rp_s1.eq(renamed_regs.rp_s1)
            m.d.comb += data_out.regs_p.rp_s2.eq(renamed_regs.rp_s2)
            self.push_instr(m, data_out)

        return m


class ROBAllocation(Elaboratable):
    """
    Module performing "ReOrder Buffer entry allocation" step of scheduling process.
    """

    def __init__(self, *, get_instr: Method, push_instr: Method, rob_put: Method, gen_params: GenParams):
        """
        Parameters
        ----------
        get_instr: Method
            Method providing instructions with physical register IDs present for all used registers.
            Uses `SchedulerLayouts.rob_allocate_in`.
        push_instr: Method
            Method used for pushing the serviced instruction to the next step.
            Uses `SchedulerLayouts.rob_allocate_out`.
        rob_put: Method
            Method used for getting a free entry in the ROB. Uses `ROBLayouts.data_layout`
            and `ROBLayouts.id_layout`.
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rob_allocate_in
        self.output_layout = layouts.rob_allocate_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rob_put = rob_put

    def elaborate(self, platform):
        m = TModule()

        data_out = Signal(self.output_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)

            rob_id = self.rob_put(
                m,
                rl_dst=instr.regs_l.rl_dst,
                rp_dst=instr.regs_p.rp_dst,
                fb_instr_idx=instr.ftq_addr.fb_instr_idx,
            )

            m.d.comb += assign(data_out, instr, fields=AssignType.COMMON)
            m.d.comb += data_out.rob_id.eq(rob_id.rob_id)

            self.push_instr(m, data_out)

        return m


class RSSelection(Elaboratable):
    """
    Module performing "Reservation Station selection" step of scheduling process.

    For each instruction it selects the first available RS capable of handling
    the given instruction. It uses multiple transactions, so it does not require all
    methods to be available at the same time.
    """

    def __init__(
        self,
        *,
        get_instr: Method,
        push_instr: Method,
        rs_select: Sequence[tuple[Method, set[OpType]]],
        gen_params: GenParams
    ):
        """
        Parameters
        ----------
        get_instr: Method
            Method providing instructions with entry in ROB. Uses `SchedulerLayouts.rs_select_in`.
        push_instr: Method
            Method used for pushing instruction with selected RS to next step.
            Uses `SchedulerLayouts.rs_select_out`.
        rs_select: Sequence[tuple[Method, set[OpType]]]
            Sequence of pairs, each representing a single RS. The components are:

            - A method used for allocating an entry in the RS. Uses `RSLayouts.select_out`.
            - A set of `OpType`\\s that can be handled by this RS.
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rs_select_in
        self.output_layout = layouts.rs_select_out

        self.get_instr = get_instr
        self.rs_select = rs_select
        self.push_instr = push_instr

    def decode_optype_set(self, optypes: set[OpType]) -> int:
        res = 0x0
        for op in optypes:
            res |= 1 << op - OpType.UNKNOWN
        return res

    def elaborate(self, platform):
        m = TModule()

        lookup = Signal(OpType)  # lookup of currently processed optype
        m.d.comb += lookup.eq(self.get_instr.data_out.exec_fn.op_type)

        data_out = Signal(self.output_layout)

        for i, (alloc, optypes) in enumerate(self.rs_select):
            # checks if RS can perform this kind of operation
            optype_matches = Cat(lookup == op for op in optypes).any()
            with Transaction().body(m, request=optype_matches):
                instr = self.get_instr(m)
                allocated_field = alloc(m)

                m.d.comb += assign(data_out, instr)
                m.d.comb += data_out.rs_entry_id.eq(allocated_field.rs_entry_id)
                m.d.comb += data_out.rs_selected.eq(i)

                self.push_instr(m, data_out)

        return m


class RSInsertion(Elaboratable):
    """
    Module performing the "Reservation Station insertion" step of the scheduling process.

    It requires all methods to be available at the same time in order to insert
    a single instruction to the RS.
    """

    def __init__(
        self,
        *,
        get_instr: Method,
        rs_insert: Sequence[Method],
        rf_read1: Method,
        rf_read2: Method,
        gen_params: GenParams
    ):
        """
        Parameters
        ----------
        get_instr: Method
            Method providing instructions with reserved entry in ROB. Uses `SchedulerLayouts.rs_insert_in`.
        rs_insert: Sequence[Method]
            Sequence of methods used for pushing an instruction into the RS. Ordering of this list
            determines the ID of a specific RS. They use `RSLayouts.insert_in`
        rf_read1: Method
            Method used for getting value of first source register and information if it is valid.
            Uses `RFLayouts.rf_read_out` and `RFLayouts.rf_read_in`.
        rf_read2: Method
            Method used for getting value of second source register and information if it is valid.
            Uses `RFLayouts.rf_read_out` and `RFLayouts.rf_read_in`.
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        self.get_instr = get_instr
        self.rs_insert = rs_insert
        self.rf_read1 = rf_read1
        self.rf_read2 = rf_read2

    def elaborate(self, platform):
        m = TModule()

        # This transaction will not be stalled by single RS because insert methods do not use conditional calling,
        # therefore we can use single transaction here.
        with Transaction().body(m):
            instr = self.get_instr(m)
            source1 = self.rf_read1(m, reg_id=instr.regs_p.rp_s1)
            source2 = self.rf_read2(m, reg_id=instr.regs_p.rp_s2)

            # when core is flushed, rp_dst are discarded.
            # source operands may never become ready, skip waiting for them in any in RSes/FBs.
            core_state = DependencyContext.get().get_dependency(CoreStateKey())
            flushing = core_state(m).flushing

            data = {
                # when operand value is valid the convention is to set operand source to 0
                "rs_data": {
                    "rp_s1": Mux(source1.valid | flushing, 0, instr.regs_p.rp_s1),
                    "rp_s2": Mux(source2.valid | flushing, 0, instr.regs_p.rp_s2),
                    "rp_s1_reg": instr.regs_p.rp_s1,
                    "rp_s2_reg": instr.regs_p.rp_s2,
                    "rp_dst": instr.regs_p.rp_dst,
                    "rob_id": instr.rob_id,
                    "exec_fn": instr.exec_fn,
                    "s1_val": Mux(source1.valid, source1.reg_val, 0),
                    "s2_val": Mux(source2.valid, source2.reg_val, 0),
                    "imm": instr.imm,
                    "csr": instr.csr,
                    "pc": instr.pc,
                    "ftq_addr": instr.ftq_addr,
                },
            }

            for i, rs_insert in enumerate(self.rs_insert):
                # connect only matching fields
                arg = Signal.like(rs_insert.data_in)
                m.d.comb += assign(arg, data, fields=AssignType.COMMON)
                # this assignment truncates signal width from max rs_entry_bits to target RS specific width
                m.d.comb += arg.rs_entry_id.eq(instr.rs_entry_id)

                with m.If(instr.rs_selected == i):
                    rs_insert(m, arg)

        return m


class Scheduler(Elaboratable):
    """
    Module responsible for preparing an instruction and its insertion into RS. It supports
    multiple RS configurations, in which case, it will send the instruction to the first
    available RS which supports this kind of instructions.

    In order to prepare instruction it performs following steps:
    - physical register allocation
    - register renaming
    - ROB entry allocation
    - RS selection
    - RS insertion

    Warnings
    --------
    Instruction without any supporting RS will get stuck and block the scheduler pipeline.
    """

    def __init__(
        self,
        *,
        get_instr: Method,
        get_free_reg: Method,
        rat_rename: Method,
        rob_put: Method,
        rf_read1: Method,
        rf_read2: Method,
        reservation_stations: Sequence[tuple[FuncBlock, set[OpType]]],
        gen_params: GenParams
    ):
        """
        Parameters
        ----------
        get_instr: Method
            Method providing decoded instructions to be scheduled for execution. It has
            layout as described by `DecodeLayouts.decoded_instr`.
        get_free_reg: Method
            Method providing the ID of a currently free physical register.
        rat_rename: Method
            Method used for renaming the source register in F-RAT. Uses `RATLayouts.rat_rename_in`
            and `RATLayouts.rat_rename_out`.
        rob_put: Method
            Method used for getting a free entry in ROB. Uses `ROBLayouts.data_layout`.
        rf_read1: Method
            Method used for getting value of first source register and information if it is valid.
            Uses `RFLayouts.rf_read_out` and `RFLayouts.rf_read_in`.
        rf_read2: Method
            Method used for getting value of second source register and information if it is valid.
            Uses `RFLayouts.rf_read_out` and `RFLayouts.rf_read_in`.
        reservation_stations: Sequence[FuncBlock]
            Sequence of units with RS interfaces to which instructions should be inserted.
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        self.layouts = self.gen_params.get(SchedulerLayouts)
        self.get_instr = get_instr
        self.get_free_reg = get_free_reg
        self.rat_rename = rat_rename
        self.rob_put = rob_put
        self.rf_read1 = rf_read1
        self.rf_read2 = rf_read2
        self.rs = reservation_stations

    def elaborate(self, platform):
        m = TModule()

        m.submodules.alloc_rename_buf = alloc_rename_buf = FIFO(self.layouts.reg_alloc_out, 2)
        m.submodules.reg_alloc = RegAllocation(
            get_instr=self.get_instr,
            push_instr=alloc_rename_buf.write,
            get_free_reg=self.get_free_reg,
            gen_params=self.gen_params,
        )

        m.submodules.rename_out_buf = rename_out_buf = Connect(self.layouts.renaming_out)
        m.submodules.renaming = Renaming(
            get_instr=alloc_rename_buf.read,
            push_instr=rename_out_buf.write,
            rename=self.rat_rename,
            gen_params=self.gen_params,
        )

        m.submodules.reg_alloc_out_buf = reg_alloc_out_buf = FIFO(self.layouts.rob_allocate_out, 2)
        m.submodules.rob_alloc = ROBAllocation(
            get_instr=rename_out_buf.read,
            push_instr=reg_alloc_out_buf.write,
            rob_put=self.rob_put,
            gen_params=self.gen_params,
        )

        m.submodules.rs_select_out_buf = rs_select_out_buf = FIFO(self.layouts.rs_select_out, 2)
        m.submodules.rs_selector = RSSelection(
            gen_params=self.gen_params,
            get_instr=reg_alloc_out_buf.read,
            rs_select=[(rs.select, optypes) for rs, optypes in self.rs],
            push_instr=rs_select_out_buf.write,
        )

        m.submodules.rs_insertion = RSInsertion(
            get_instr=rs_select_out_buf.read,
            rs_insert=[rs.insert for rs, _ in self.rs],
            rf_read1=self.rf_read1,
            rf_read2=self.rf_read2,
            gen_params=self.gen_params,
        )

        return m
