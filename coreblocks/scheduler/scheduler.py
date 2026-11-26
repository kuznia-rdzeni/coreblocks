from collections.abc import Sequence

from amaranth import *
from amaranth.lib.data import ArrayLayout, View

from transactron import Method, Methods, Required, Transaction, TModule
from transactron.lib import Connect, WideFifo
from transactron.lib.metrics import TaggedCounter
from transactron.lib.pipeline import PipelineBuilder
from transactron.utils import LayoutListField, OneHotMux, logging, assign, AssignType
from transactron.utils.dependencies import DependencyContext
from transactron.utils.transactron_helpers import from_layout_field

from transactron.evlog import EventSource

from coreblocks.interface.layouts import (
    CommonLayoutFields,
    RATLayouts,
    RFLayouts,
    ROBLayouts,
    RSFullDataLayout,
    SchedulerLayouts,
)
from coreblocks.params import GenParams
from coreblocks.arch.optypes import OpType, impure_optypes
from coreblocks.interface.keys import CoreStateKey, RVVIHartCollectorKey
from coreblocks.telemetry import RobAllocate, SchedulerEnter

__all__ = ["Scheduler"]


log = logging.HardwareLogger("frontend.scheduler")
evlog = EventSource("backend.scheduler")


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

        fields = self.gen_params.get(CommonLayoutFields)
        layouts = self.gen_params.get(SchedulerLayouts)

        def col(field: LayoutListField) -> tuple[str, ArrayLayout]:
            """Column (one value per instruction) version of a layout field."""
            name, shape = field
            return (name, ArrayLayout(from_layout_field(shape), self.gen_params.frontend_superscalarity))

        m.submodules.perf_rs_selection_count = perf_rs_selection_count = TaggedCounter(
            "frontend.scheduler.rs_selection_count",
            description="Number of instructions inserted into RSs in one cycle",
            tags=range(self.gen_params.frontend_superscalarity + 1),
        )

        m.submodules.pipeline = pb = PipelineBuilder()

        # Instructions are received in row representation ({count, data[...]}) and are
        # converted to column representation (one array of values per field).
        pb.call_method(self.get_instr, transpose=["data"])
        pb.connector(Connect)

        # Register allocation: allocate a physical register for the instruction result.
        @pb.stage(m, o=[col(fields.rp_dst)])
        def _(count: Value, regs_l: View, ftq_ptr: View, ftq_offset: View):
            rp_dst = Signal(ArrayLayout(self.gen_params.phys_regs_bits, self.gen_params.frontend_superscalarity))
            for i in range(self.gen_params.frontend_superscalarity):
                evlog.emit(m, SchedulerEnter.hw(ftq_ptr=ftq_ptr[i], ftq_offset=ftq_offset[i]), when=i < count)
                with m.If((i < count) & (regs_l[i].rl_dst != 0)):
                    m.d.av_comb += rp_dst[i].eq(self.get_free_reg[i](m).ident)
            return {"rp_dst": rp_dst}

        # Instruction tagging, see `CheckpointRAT.tag`. Tag is common for the whole group.
        # Jump insn always last in group - commit_checkpoint is set there.
        # Tag increment happens after jump or flush - first insn in group.
        @pb.stage(m, o=[fields.tag, fields.tag_increment, fields.commit_checkpoint])
        def _(count: Value, rollback_tag: View, rollback_tag_v: View, commit_checkpoint: View):
            idx = Signal(range(self.gen_params.frontend_superscalarity))
            m.d.av_comb += idx.eq(count - 1)
            return self.crat_tag(
                m,
                rollback_tag=rollback_tag[idx],
                rollback_tag_v=rollback_tag_v[idx],
                commit_checkpoint=commit_checkpoint[idx],
            )

        # Renaming source registers (logical to physical), updating F-RAT with the destination register.
        @pb.stage(m, o=[col(fields.rp_s1), col(fields.rp_s2)])
        def _(count: Value, tag: Value, commit_checkpoint: Value, regs_l: View, rp_dst: View):
            self.crat_commit_checkpoint(m, tag=tag, commit_checkpoint=commit_checkpoint)
            rp_s1 = Signal(ArrayLayout(self.gen_params.phys_regs_bits, self.gen_params.frontend_superscalarity))
            rp_s2 = Signal(ArrayLayout(self.gen_params.phys_regs_bits, self.gen_params.frontend_superscalarity))
            for i in range(self.gen_params.frontend_superscalarity):
                with m.If(i < count):
                    renamed = self.crat_rename[i](
                        m,
                        rl_s1=regs_l[i].rl_s1,
                        rl_s2=regs_l[i].rl_s2,
                        rl_dst=regs_l[i].rl_dst,
                        rp_dst=rp_dst[i],
                    )
                    m.d.av_comb += rp_s1[i].eq(renamed.rp_s1)
                    m.d.av_comb += rp_s2[i].eq(renamed.rp_s2)
            return {"rp_s1": rp_s1, "rp_s2": rp_s2}

        pb.connector(Connect)

        # ROB entry allocation. From now on, instructions are handled individually,
        # so the tag is broadcast to all instructions.
        @pb.stage(m, o=[col(fields.rob_id), col(fields.tag)])
        def _(
            count: Value,
            exec_fn: View,
            regs_l: View,
            rp_dst: View,
            tag: Value,
            tag_increment: Value,
            ftq_ptr: View,
            ftq_offset: View,
        ):
            rvvi = DependencyContext.get().get_optional_dependency(RVVIHartCollectorKey())

            rob_ids = self.rob_put(
                m,
                count=count,
                entries=[
                    {
                        "rob_data": {
                            "rl_dst": regs_l[i].rl_dst,
                            "rp_dst": rp_dst[i],
                            "tag_increment": tag_increment if i == 0 else 0,
                            "ftq_ptr": ftq_ptr[i],
                        },
                        "pure": ~Cat(exec_fn[i].op_type == op_type for op_type in impure_optypes).any(),
                    }
                    for i in range(self.gen_params.frontend_superscalarity)
                ],
            )

            rob_id = Signal(ArrayLayout(self.gen_params.rob_entries_bits, self.gen_params.frontend_superscalarity))
            tags = Signal(ArrayLayout(self.gen_params.tag_bits, self.gen_params.frontend_superscalarity))
            for i in range(self.gen_params.frontend_superscalarity):
                m.d.av_comb += rob_id[i].eq(rob_ids.entries[i].rob_id)
                m.d.av_comb += tags[i].eq(tag)

                evlog.emit(
                    m,
                    RobAllocate.hw(ftq_ptr=ftq_ptr[i], ftq_offset=ftq_offset[i], rob_id=rob_id[i], rp_dst=rp_dst[i]),
                    when=i < count,
                )

                if rvvi is not None:
                    with m.If(i < count):
                        rvvi.register_ftq_rob_assoc[i](
                            m, rob_id=rob_id[i], ftq_ptr=ftq_ptr[i], ftq_offset=ftq_offset[i]
                        )

            return {"rob_id": rob_id, "tag": tags}

        m.submodules.rs_select_in_buf = rs_select_in_buf = WideFifo(
            layouts.rs_select_in_data,
            2 * self.gen_params.frontend_superscalarity,
            self.gen_params.frontend_superscalarity,
        )

        pb.connector(Connect)
        pb.call_method(rs_select_in_buf.write, transpose=["data"])

        m.submodules.rs_pipeline = rs_pb = PipelineBuilder()

        # RS selection: for each instruction, select the first available RS capable of handling it.
        # Instructions are selected in order; the selected prefix is consumed from the FIFO.
        # Multiple transactions are used, so not all RSs need to be available at the same time.
        @rs_pb.stage(
            m,
            o=[
                ("count", range(self.gen_params.frontend_superscalarity + 1)),
                ("data", ArrayLayout(layouts.rs_select_in_data, self.gen_params.frontend_superscalarity)),
                col(layouts.rs_entry_id),
                col(layouts.rs_selected),
            ],
            transpose=["data"],
        )
        def _():
            instrs = rs_select_in_buf.peek(m)
            selected_count = Signal(range(self.gen_params.frontend_superscalarity + 1))
            rs_entry_id = Signal(
                ArrayLayout(self.gen_params.max_rs_entries_bits, self.gen_params.frontend_superscalarity)
            )
            rs_selected = Signal(ArrayLayout(self.gen_params.rs_number_bits, self.gen_params.frontend_superscalarity))

            prev_insert: Value = C(1)
            for i in range(self.gen_params.frontend_superscalarity):
                next_insert = Signal()
                lookup = Signal(OpType)  # lookup of currently processed optype
                m.d.av_comb += lookup.eq(instrs.data[i].exec_fn.op_type)
                optype_matches_list: list[Value] = []

                for j, (rs_select, block_params) in enumerate(zip(self.rs_select, self.gen_params.func_units_config)):
                    # checks if RS can perform this kind of operation
                    optype_matches = Cat(lookup == op for op in block_params.get_optypes()).any()
                    optype_matches_list.append(optype_matches)
                    with Transaction(name=f"RSSelection_{i}_{j}").body(
                        m, ready=(i < instrs.count) & prev_insert & optype_matches
                    ):
                        # Transactron guarantees each RS will only be allocated once
                        m.d.comb += rs_entry_id[i].eq(rs_select(m).rs_entry_id)
                        m.d.comb += rs_selected[i].eq(j)
                        m.d.comb += next_insert.eq(1)

                        self.rf_read_req[2 * i](m, instrs.data[i].rp_s1)
                        self.rf_read_req[2 * i + 1](m, instrs.data[i].rp_s2)

                with m.If(i < instrs.count):
                    log.assertion(m, Cat(optype_matches_list).any(), "optype {} didn't match any RS", lookup)

                with m.If(next_insert):
                    m.d.av_comb += selected_count.eq(i + 1)

                prev_insert = next_insert

            rs_select_in_buf.read(m, count=selected_count)
            perf_rs_selection_count.incr(m, tag=selected_count)
            return {
                "count": selected_count,
                "data": instrs.data,
                "rs_entry_id": rs_entry_id,
                "rs_selected": rs_selected,
            }

        # RS insertion. Requires all RS insert methods to be available at the same time.
        # It will not be stalled by a single RS because insert methods are not called conditionally.
        @rs_pb.stage(m)
        def _(
            count: Value,
            exec_fn: View,
            rp_s1: View,
            rp_s2: View,
            rp_dst: View,
            rob_id: View,
            imm: View,
            csr: View,
            pc: View,
            tag: View,
            ftq_ptr: View,
            rs_entry_id: View,
            rs_selected: View,
        ):
            # when core is flushed, rp_dst are discarded.
            # source operands may never become ready, skip waiting for them in any in RSes/FBs.
            # it could happen when rp is already announced and freed in RF due to flushing, but remaining
            # instructions could still depend on it.
            flushing = DependencyContext.get().get_dependency(CoreStateKey())(m).flushing
            active_tags = self.crat_active_tags(m)
            rs_datas: list[View] = []

            for i in range(self.gen_params.frontend_superscalarity):
                skip_source_registers = flushing | ~active_tags.active_tags[tag[i]]

                # RS insertion guarantees RF response for present instructions
                # Nested transaction used to avoid locking
                with (tr := Transaction()).body(m):
                    source1 = self.rf_read_resp[2 * i](m, reg_id=rp_s1[i])
                    source2 = self.rf_read_resp[2 * i + 1](m, reg_id=rp_s2[i])
                log.assertion(m, tr.run == (i < count), f"invalid RF response for instr {i}")

                rs_data = Signal(self.gen_params.get(RSFullDataLayout).data_layout)
                m.d.av_comb += assign(
                    rs_data,
                    {
                        # when operand value is valid the convention is to set operand source to 0
                        "rp_s1": Mux(source1.valid | skip_source_registers, 0, rp_s1[i]),
                        "rp_s2": Mux(source2.valid | skip_source_registers, 0, rp_s2[i]),
                        "rp_s1_reg": rp_s1[i],
                        "rp_s2_reg": rp_s2[i],
                        "rp_dst": rp_dst[i],
                        "rob_id": rob_id[i],
                        "exec_fn": exec_fn[i],
                        "s1_val": Mux(source1.valid, source1.reg_val, 0),
                        "s2_val": Mux(source2.valid, source2.reg_val, 0),
                        "imm": imm[i],
                        "csr": csr[i],
                        "pc": pc[i],
                        "tag": tag[i],
                        "ftq_ptr": ftq_ptr[i],
                    },
                )
                rs_datas.append(rs_data)

            for j, rs_insert in enumerate(self.rs_insert):
                # because instrs come from RS selection, this is guaranteed one-hot or zero
                matches = Signal(self.gen_params.frontend_superscalarity)
                m.d.av_comb += matches.eq(
                    Cat((i < count) & (rs_selected[i] == j) for i in range(self.gen_params.frontend_superscalarity))
                )

                matched_rs_data = OneHotMux.create(m, [(matches[i], rs_datas[i]) for i in range(len(matches))])
                matched_entry_id = OneHotMux.create(m, [(matches[i], rs_entry_id[i]) for i in range(len(matches))])

                arg = Signal.like(rs_insert.data_in)
                # connect only matching fields
                m.d.av_comb += assign(arg.rs_data, matched_rs_data, fields=AssignType.COMMON)
                # this assignment truncates signal width from max rs_entry_bits to target RS specific width
                m.d.av_comb += arg.rs_entry_id.eq(matched_entry_id)

                with m.If(matches.any()):
                    rs_insert(m, arg)

        return m
