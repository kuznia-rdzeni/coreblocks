from collections.abc import Sequence

from amaranth import *

from transactron import Method, Methods, Required, Transaction, TModule
from transactron.lib import Connect, Pipe, WideFifo
from transactron.utils import OneHotSwitchDynamic, assign, AssignType
from transactron.utils.dependencies import DependencyContext

from coreblocks.interface.layouts import RATLayouts, RFLayouts, ROBLayouts, RSFullDataLayout, SchedulerLayouts
from coreblocks.params import GenParams
from coreblocks.arch.optypes import OpType
from coreblocks.interface.keys import CoreStateKey

__all__ = ["Scheduler"]


class RegAllocation(Elaboratable):
    """
    Module performing the "Register allocation" step (allocating a physical register for
    the instruction result). A part of the scheduling process.
    """

    get_instrs: Required[Method]
    push_instrs: Required[Method]
    get_free_reg: Required[Methods]

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)

        self.get_instrs = Method(o=layouts.reg_alloc_in)
        self.push_instrs = Method(i=layouts.reg_alloc_out)
        self.get_free_reg = Methods(gen_params.frontend_superscalarity, o=layouts.free_rf_layout)

    def elaborate(self, platform):
        m = TModule()

        data_out = Signal(self.push_instrs.layout_in)

        with Transaction().body(m):
            instrs = self.get_instrs(m)
            m.d.av_comb += assign(data_out, instrs)

            for i in range(self.gen_params.frontend_superscalarity):
                with m.If((i < instrs.count) & (instrs.data[i].regs_l.rl_dst != 0)):
                    m.d.av_comb += data_out.data[i].regs_p.rp_dst.eq(self.get_free_reg[i](m).ident)

            self.push_instrs(m, data_out)

        return m


class InstructionTagger(Elaboratable):
    """
    `Scheduler` driver of `CheckpointRAT` `tag` stage. See `CheckpointRAT.tag` for description.
    """

    get_instrs: Required[Method]
    push_instrs: Required[Method]
    crat_tag: Required[Method]

    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)

        self.get_instrs = Method(o=layouts.instr_tag_in)
        self.push_instrs = Method(i=layouts.instr_tag_out)
        self.crat_tag = Method(i=gen_params.get(RATLayouts).crat_tag_in, o=gen_params.get(RATLayouts).crat_tag_out)

    def elaborate(self, platform):
        m = TModule()

        data_out = Signal(self.push_instrs.layout_in)

        with Transaction().body(m):
            instrs = self.get_instrs(m)

            idx = Signal(range(self.gen_params.frontend_superscalarity))
            m.d.av_comb += idx.eq(instrs.count - 1)

            tag_out = self.crat_tag(
                m,
                rollback_tag=instrs.data[idx].rollback_tag,
                rollback_tag_v=instrs.data[idx].rollback_tag_v,
                commit_checkpoint=instrs.data[idx].commit_checkpoint,
            )

            m.d.av_comb += assign(data_out, instrs, fields=AssignType.COMMON)

            for i in range(self.gen_params.frontend_superscalarity):
                m.d.av_comb += data_out.data[i].tag.eq(tag_out.tag)

            # Jump insn always last in group - commit_checkpoint is set there
            # Tag increment happens after jump or flush - first insn in group
            m.d.av_comb += data_out.data[0].tag_increment.eq(tag_out.tag_increment)
            m.d.av_comb += data_out.data[idx].commit_checkpoint.eq(tag_out.commit_checkpoint)

            self.push_instrs(m, data_out)

        return m


class Renaming(Elaboratable):
    """
    Module performing the "Renaming source register" (translation from logical register
    name to physical register name) step of the scheduling process. Additionally it updates
    the F-RAT with the translation from the logical destination register ID to the physical ID.
    """

    get_instrs: Required[Method]
    push_instrs: Required[Method]
    crat_commit_checkpoint: Required[Method]
    rename: Required[Methods]

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)

        self.get_instrs = Method(o=layouts.renaming_in)
        self.push_instrs = Method(i=layouts.renaming_out)
        self.crat_commit_checkpoint = Method(i=gen_params.get(RATLayouts).crat_commit_checkpoint_in)
        self.rename = Methods(
            gen_params.frontend_superscalarity,
            i=gen_params.get(RATLayouts).crat_rename_in,
            o=gen_params.get(RATLayouts).crat_rename_out,
        )

    def elaborate(self, platform):
        m = TModule()

        data_out = Signal(self.push_instrs.layout_in)

        with Transaction().body(m):
            instrs = self.get_instrs(m)

            m.d.av_comb += data_out.count.eq(instrs.count)

            idx = Signal(range(self.gen_params.frontend_superscalarity))
            m.d.av_comb += idx.eq(instrs.count - 1)

            # tag is the same for all instrs
            self.crat_commit_checkpoint(m, tag=instrs.data[0].tag, commit_checkpoint=instrs.data[idx].commit_checkpoint)

            for i in range(self.gen_params.frontend_superscalarity):
                instr = instrs.data[i]
                instr_out = data_out.data[i]

                with m.If(i < instrs.count):
                    renamed_regs = self.rename[i](
                        m,
                        rl_s1=instr.regs_l.rl_s1,
                        rl_s2=instr.regs_l.rl_s2,
                        rl_dst=instr.regs_l.rl_dst,
                        rp_dst=instr.regs_p.rp_dst,
                    )

                m.d.av_comb += assign(instr_out, instr, fields={"exec_fn", "imm", "csr", "pc", "tag", "tag_increment"})
                m.d.av_comb += assign(instr_out.regs_l, instr.regs_l, fields=AssignType.COMMON)
                m.d.av_comb += instr_out.regs_p.rp_dst.eq(instr.regs_p.rp_dst)
                m.d.av_comb += instr_out.regs_p.rp_s1.eq(renamed_regs.rp_s1)
                m.d.av_comb += instr_out.regs_p.rp_s2.eq(renamed_regs.rp_s2)

            self.push_instrs(m, data_out)

        return m


class ROBAllocation(Elaboratable):
    """
    Module performing "ReOrder Buffer entry allocation" step of scheduling process.
    """

    get_instrs: Required[Method]
    push_instrs: Required[Method]
    rob_put: Required[Method]

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)

        self.get_instrs = Method(o=layouts.rob_allocate_in)
        self.push_instrs = Method(i=layouts.rob_allocate_out)
        self.rob_put = Method(i=gen_params.get(ROBLayouts).put_layout, o=gen_params.get(ROBLayouts).put_out_layout)

    def elaborate(self, platform):
        m = TModule()

        data_out = Signal(self.push_instrs.layout_in)

        with Transaction().body(m):
            instrs = self.get_instrs(m)

            rob_ids = self.rob_put(
                m,
                count=instrs.count,
                entries=[
                    {
                        "rl_dst": instr.regs_l.rl_dst,
                        "rp_dst": instr.regs_p.rp_dst,
                        "tag_increment": instr.tag_increment,
                    }
                    for instr in instrs.data
                ],
            )

            m.d.av_comb += assign(data_out, instrs, fields=AssignType.COMMON)
            for i in range(self.gen_params.frontend_superscalarity):
                m.d.av_comb += data_out.data[i].rob_id.eq(rob_ids.entries[i].rob_id)

            self.push_instrs(m, data_out)

        return m


class RSSelection(Elaboratable):
    """
    Module performing "Reservation Station selection" step of scheduling process.

    For each instruction it selects the first available RS capable of handling
    the given instruction. It uses multiple transactions, so it does not require all
    methods to be available at the same time.
    """

    get_instrs: Required[Method]
    peek_instrs: Required[Method]
    push_instrs: Required[Method]
    rf_read_req: Required[Methods]
    rs_select: Required[Sequence[Method]]

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        layouts = gen_params.get(SchedulerLayouts)

        self.get_instrs = Method(i=[("count", range(gen_params.frontend_superscalarity + 1))], o=layouts.rs_select_in)
        self.peek_instrs = Method(o=layouts.rs_select_in)
        self.push_instrs = Method(i=layouts.rs_select_out)
        self.rf_read_req = Methods(2 * gen_params.frontend_superscalarity, i=gen_params.get(RFLayouts).rf_read_in)
        self.rs_select = [Method(o=conf.get_layouts(gen_params).select_out) for conf in gen_params.func_units_config]

    def decode_optype_set(self, optypes: set[OpType]) -> int:
        res = 0x0
        for op in optypes:
            res |= 1 << op - OpType.UNKNOWN
        return res

    def elaborate(self, platform):
        m = TModule()

        count = Signal(range(self.gen_params.frontend_superscalarity + 1))
        data_out = Signal(self.push_instrs.layout_in)

        with Transaction().body(m):
            instrs = self.peek_instrs(m)
            m.d.av_comb += data_out.count.eq(count)

            prev_insert: Value = C(1)

            for i in range(self.gen_params.frontend_superscalarity):
                next_insert = Signal()
                instr = instrs.data[i]
                instr_out = data_out.data[i]
                lookup = Signal(OpType)  # lookup of currently processed optype
                m.d.av_comb += lookup.eq(instr.exec_fn.op_type)
                m.d.av_comb += assign(instr_out, instr)

                for j, (alloc, block_params) in enumerate(zip(self.rs_select, self.gen_params.func_units_config)):
                    # checks if RS can perform this kind of operation
                    optype_matches = Cat(lookup == op for op in block_params.get_optypes()).any()
                    with Transaction().body(m, ready=(i < instrs.count) & prev_insert & optype_matches):
                        allocated_field = alloc(m)

                        m.d.comb += instr_out.rs_entry_id.eq(allocated_field.rs_entry_id)
                        m.d.comb += instr_out.rs_selected.eq(j)

                        m.d.comb += next_insert.eq(1)

                        self.rf_read_req[2 * i](m, instr.regs_p.rp_s1)
                        self.rf_read_req[2 * i + 1](m, instr.regs_p.rp_s2)

                with m.If(next_insert):
                    m.d.av_comb += count.eq(i + 1)

                prev_insert = next_insert

            self.get_instrs(m, count=count)
            self.push_instrs(m, data_out)

        return m


class RSInsertion(Elaboratable):
    """
    Module performing the "Reservation Station insertion" step of the scheduling process.

    It requires all methods to be available at the same time in order to insert
    a single instruction to the RS.
    """

    get_instrs: Required[Method]
    rf_read_resp: Required[Methods]
    crat_active_tags: Required[Method]
    rs_insert: Required[Sequence[Method]]

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params

        layouts = gen_params.get(SchedulerLayouts)

        self.get_instrs = Method(o=layouts.rs_insert_in)
        self.rf_read_resp = Methods(
            2 * gen_params.frontend_superscalarity,
            i=gen_params.get(RFLayouts).rf_read_in,
            o=gen_params.get(RFLayouts).rf_read_out,
        )
        self.crat_active_tags = Method(o=gen_params.get(RATLayouts).get_active_tags_out)
        self.rs_insert = [Method(i=conf.get_layouts(gen_params).insert_in) for conf in gen_params.func_units_config]

    def elaborate(self, platform):
        m = TModule()

        # This transaction will not be stalled by single RS because insert methods do not use conditional calling,
        # therefore we can use single transaction here.
        with Transaction().body(m):
            instrs = self.get_instrs(m)

            # when core is flushed, rp_dst are discarded.
            # source operands may never become ready, skip waiting for them in any in RSes/FBs.
            # it could happen when rp is already announced and freed in RF due to flushing, but remaining instructions
            # could still depend on it.

            core_state = DependencyContext.get().get_dependency(CoreStateKey())
            flushing = core_state(m).flushing

            tag_inactive = ~self.crat_active_tags(m).active_tags[instrs.data[0].tag]

            skip_source_registers = flushing | tag_inactive

            rs_entry_id: list[Value] = []
            rs_selected: list[Value] = []
            rs_datas = []

            for i in range(self.gen_params.frontend_superscalarity):
                instr = instrs.data[i]
                with Transaction().body(m):
                    source1 = self.rf_read_resp[2 * i](m, reg_id=instr.regs_p.rp_s1)
                    source2 = self.rf_read_resp[2 * i + 1](m, reg_id=instr.regs_p.rp_s2)
                # TODO: assert that if i < count, transaction runs

                rs_data = Signal(self.gen_params.get(RSFullDataLayout).data_layout)
                m.d.av_comb += assign(
                    rs_data,
                    {
                        # when operand value is valid the convention is to set operand source to 0
                        "rp_s1": Mux(source1.valid | skip_source_registers, 0, instr.regs_p.rp_s1),
                        "rp_s2": Mux(source2.valid | skip_source_registers, 0, instr.regs_p.rp_s2),
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
                        "tag": instr.tag,
                    },
                )
                rs_datas.append(rs_data)
                rs_entry_id.append(instr.rs_entry_id)
                rs_selected.append(instr.rs_selected)

            for j, rs_insert in enumerate(self.rs_insert):
                # because instrs come from RS selection, this is guaranteed one-hot or zero
                matches = Signal(self.gen_params.frontend_superscalarity)
                m.d.av_comb += matches.eq(
                    Cat(
                        (i < instrs.count) & (rs_selected[i] == j)
                        for i in range(self.gen_params.frontend_superscalarity)
                    )
                )

                arg = Signal.like(rs_insert.data_in)
                for i in OneHotSwitchDynamic(m, matches):
                    # connect only matching fields
                    m.d.av_comb += assign(arg.rs_data, rs_datas[i], fields=AssignType.COMMON)
                    # this assignment truncates signal width from max rs_entry_bits to target RS specific width
                    m.d.av_comb += arg.rs_entry_id.eq(rs_entry_id[i])

                with m.If(matches.any()):
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

    get_instr: Required[Method]
    """
    Method providing decoded instructions to be scheduled for execution. It has layout as described
    by `SchedulerLayouts.scheduler_in`.
    """

    get_free_reg: Required[Methods]
    """Provides the ID of a currently free physical register."""

    crat_commit_checkpoint: Required[Method]
    """Handles tags and checkpoints in C-RAT while renaming.."""

    crat_rename: Required[Methods]
    """Renames the source register in C-RAT."""

    crat_tag: Required[Method]
    """Tags instructions to checkpoints in C-RAT."""

    crat_active_tags: Required[Method]
    """Gets information about tags that are on current speculation path from C-RAT."""

    rob_put: Required[Method]
    """Gets a free entry in ROB."""

    rf_read_req: Required[Methods]
    """Requests value of a source register."""

    rf_read_resp: Required[Methods]
    """Gets requested value of a source register and information if it is valid."""

    rs_select: Required[Sequence[Method]]
    """Selects RS slot."""

    rs_insert: Required[Sequence[Method]]
    """Inserts instruction into RS slot."""

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        """
        self.gen_params = gen_params
        self.layouts = self.gen_params.get(SchedulerLayouts)
        self.get_instr = Method(o=self.layouts.scheduler_in)
        self.get_free_reg = Methods(gen_params.frontend_superscalarity, o=self.layouts.free_rf_layout)
        self.crat_commit_checkpoint = Method(i=gen_params.get(RATLayouts).crat_commit_checkpoint_in)
        self.crat_rename = Methods(
            gen_params.frontend_superscalarity,
            i=gen_params.get(RATLayouts).crat_rename_in,
            o=gen_params.get(RATLayouts).crat_rename_out,
        )
        self.crat_active_tags = Method(o=gen_params.get(RATLayouts).get_active_tags_out)
        self.crat_tag = Method(i=gen_params.get(RATLayouts).crat_tag_in, o=gen_params.get(RATLayouts).crat_tag_out)
        self.rob_put = Method(i=gen_params.get(ROBLayouts).put_layout, o=gen_params.get(ROBLayouts).put_out_layout)
        self.rf_read_req = Methods(2 * gen_params.frontend_superscalarity, i=gen_params.get(RFLayouts).rf_read_in)
        self.rf_read_resp = Methods(
            2 * gen_params.frontend_superscalarity,
            i=gen_params.get(RFLayouts).rf_read_in,
            o=gen_params.get(RFLayouts).rf_read_out,
        )
        self.rs_select = [Method(o=conf.get_layouts(gen_params).select_out) for conf in gen_params.func_units_config]
        self.rs_insert = [Method(i=conf.get_layouts(gen_params).insert_in) for conf in gen_params.func_units_config]

    def elaborate(self, platform):
        m = TModule()

        # This could be ideally changed to Connect, but unfortunately causes comb loop
        m.submodules.alloc_rename_buf = alloc_rename_buf = Pipe(self.layouts.reg_alloc_out)
        m.submodules.reg_alloc = reg_alloc = RegAllocation(gen_params=self.gen_params)
        reg_alloc.get_instrs.provide(self.get_instr)
        reg_alloc.push_instrs.provide(alloc_rename_buf.write)
        reg_alloc.get_free_reg.provide(self.get_free_reg)

        m.submodules.instr_tag_buf = instr_tag_buf = Pipe(self.layouts.instr_tag_out)
        m.submodules.instr_tag = instr_tag = InstructionTagger(gen_params=self.gen_params)
        instr_tag.get_instrs.provide(alloc_rename_buf.read)
        instr_tag.push_instrs.provide(instr_tag_buf.write)
        instr_tag.crat_tag.provide(self.crat_tag)

        m.submodules.rename_out_buf = rename_out_buf = Connect(self.layouts.renaming_out)
        m.submodules.renaming = renaming = Renaming(gen_params=self.gen_params)
        renaming.get_instrs.provide(instr_tag_buf.read)
        renaming.push_instrs.provide(rename_out_buf.write)
        renaming.crat_commit_checkpoint.provide(self.crat_commit_checkpoint)
        renaming.rename.provide(self.crat_rename)

        m.submodules.rob_alloc_out_buf = rob_alloc_out_buf = WideFifo(
            self.layouts.rs_select_in_data,
            2 * self.gen_params.frontend_superscalarity,
            self.gen_params.frontend_superscalarity,
        )
        m.submodules.rob_alloc = rob_alloc = ROBAllocation(gen_params=self.gen_params)

        rob_alloc.get_instrs.provide(rename_out_buf.read)
        rob_alloc.push_instrs.provide(rob_alloc_out_buf.write)
        rob_alloc.rob_put.provide(self.rob_put)

        m.submodules.rs_select_out_buf = rs_select_out_buf = Pipe(self.layouts.rs_select_out)
        m.submodules.rs_selector = rs_selector = RSSelection(gen_params=self.gen_params)

        rs_selector.get_instrs.provide(rob_alloc_out_buf.read)
        rs_selector.peek_instrs.provide(rob_alloc_out_buf.peek)
        rs_selector.push_instrs.provide(rs_select_out_buf.write)
        rs_selector.rf_read_req.provide(self.rf_read_req)
        for rs_select, rs_select_impl in zip(rs_selector.rs_select, self.rs_select):
            rs_select.provide(rs_select_impl)

        m.submodules.rs_insertion = rs_insertion = RSInsertion(gen_params=self.gen_params)
        rs_insertion.get_instrs.provide(rs_select_out_buf.read)
        rs_insertion.rf_read_resp.provide(self.rf_read_resp)
        rs_insertion.crat_active_tags.provide(self.crat_active_tags)
        for rs_insert, rs_insert_impl in zip(rs_insertion.rs_insert, self.rs_insert):
            rs_insert.provide(rs_insert_impl)

        return m
