from amaranth import *
from amaranth.lib.data import ArrayLayout
from amaranth.utils import ceil_log2

from transactron.core import *
from transactron.lib import logging
from transactron.lib.connectors import Pipe
from transactron.lib.metrics import HwExpHistogram
from transactron.lib.simultaneous import condition
from transactron.lib.storage import MemoryBank
from transactron.utils import DependencyContext, assign, cyclic_mask, mod_incr, popcount

from coreblocks.params import GenParams
from coreblocks.interface.layouts import RATLayouts
from coreblocks.interface.keys import CoreStateKey, RollbackKey

log = logging.HardwareLogger("core_structs.crat")


class CheckpointRAT(Elaboratable):
    """Checkpoint RAT
    Register Alias Table that supports saving (checkpointing) and rolling back its state.
    It is an replacement of plain Frontend-RAT (FRAT).

    It contains two pipelined stages `tag` and `rename`, placed in `Scheduler`. See attributes description for details.
    `tag` for instruction must be executed at least one cycle before `rename`.

    There are two resources allocated: "virtual" speculation tags, which are monotonic, issued and freed in-order,
    used to track if instructions are on valid speculation path in the core;
    and checkpoints, which are physical saved FRAT states, used for rollbacks.
    Checkpoints are freed immediately while tags are only marked as non-active, but still allocated until free in
    `Retirement`. Checkpoints are tied to some tags.

    Attributes
    ----------
    free_tag: Method
        Free a tag that is no longer referenced in the core.
        Associated checkpoints are freed too.
        This method accepts no arguments, because all tags must be freed in-order, so call means freeing
        oldest issued tag.
    get_active_tags: Method
        Gets bit array of tags that are currently active.
        If bit is set it means that a tag is on a valid
        speculation path.
    tag: Method
        Tag stage of CheckpointRAT. Issues instruction speculation tags.
        It needs rollback_tag information from core `Frontend`, that identifies first instruction fetched after
        rollback and fetch redirect. Information if checkpoint should be created after given instruction is expected
        to be provided from previous stage.
        It manages allocating new tags, scheduler flushing, information for unlocking FRAT
        and stalling the pipeline in case FRAT is not yet restored.
    rename: Method
        Rename stage of CheckpointRAT. Works like FRAT rename.
        Renames source registers and updates destination register mapping on valid tagged instructions.
        It is responsible for saving checkpoints after instruction (with commit_checkpoint flag) rename.
    flush_restore: Method
        Subset of `rename`. Used for restoring RAT state from Retirement on hard flushes.
        Blocks until restores are safe to be made. `rollback` must not be called after first restore.
    rollback: Method
        Rollback listener automatically registered to `RollbackKey`.
        Invalidates tags, frees checkpoints, initiates FRAT restore and Scheduler flushing.
    """

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        # Checkpoint count = 1 is not currently possible because of how retirement freeing works
        assert gen_params.checkpoint_count > 1

        self.frat_layout = ArrayLayout(gen_params.phys_regs_bits, gen_params.isa.reg_cnt)
        self.frat = Signal(self.frat_layout)

        layouts = gen_params.get(RATLayouts)
        self.tag = Method(i=layouts.crat_tag_in, o=layouts.crat_tag_out)
        self.rename = Method(i=layouts.crat_rename_in, o=layouts.crat_rename_out)
        self.flush_restore = Method(i=layouts.crat_flush_restore)

        self.rollback = Method(i=layouts.rollback_in)
        self.dm = DependencyContext.get()
        self.dm.add_dependency(RollbackKey(), self.rollback)

        self.free_tag = Method()
        self.get_active_tags = Method(o=layouts.get_active_tags_out)

    def elaborate(self, platform):
        m = TModule()

        # ------------------------
        # Internal data structres
        # ------------------------

        # Initialize with one allocated, active, but not checkpointed tag 0
        # With current freeing mechanism one tag must always be allocated, so head==tail -> full
        tags_head = Signal(self.gen_params.tag_bits, init=1)
        tags_tail = Signal.like(tags_head, init=0)

        checkpoints_head = Signal(range(self.gen_params.checkpoint_count), init=0)
        checkpoints_tail = Signal.like(checkpoints_head)
        checkpoints_full = Signal()

        active_tags = Signal(2**self.gen_params.tag_bits, init=1)
        checkpointed_tags = Signal(2**self.gen_params.tag_bits, init=0)

        storage = MemoryBank(shape=self.frat_layout, depth=self.gen_params.checkpoint_count)
        tag_map = MemoryBank(
            shape=range(self.gen_params.checkpoint_count),
            depth=2**self.gen_params.tag_bits,
        )

        rollback_just_started = Signal()
        rollback_target_tag = Signal(self.gen_params.tag_bits)

        frat_lock = Signal()
        frat_unlock_tag = Signal(self.gen_params.tag_bits + 1)

        last_rollback_finished = Signal(init=1)

        # ---------------------------------------
        # Internal tag and checkpoint allocation
        # ---------------------------------------

        allocate_tag = Method(i=[("active", 1)], o=[("tag", self.gen_params.tag_bits)])

        next_tag = Signal.like(tags_head)
        m.d.comb += next_tag.eq(tags_head + 1)

        next_checkpoint = Signal.like(checkpoints_head)
        m.d.comb += next_checkpoint.eq(mod_incr(checkpoints_head, self.gen_params.checkpoint_count))

        checkpoints_full_overwrite = Signal()
        checkpoints_next_tail_comb = Signal.like(checkpoints_tail)
        m.d.comb += checkpoints_next_tail_comb.eq(checkpoints_tail)

        active_tags_set_mask = Signal.like(active_tags, init=0)

        @def_method(m, allocate_tag, ready=tags_head != tags_tail)
        def _(active):
            m.d.sync += tags_head.eq(next_tag)
            m.d.comb += active_tags_set_mask.eq(active << tags_head)

            log.debug(m, True, "tag allocated 0x{:x}", tags_head)
            return tags_head

        allocate_checkpoint = Method(o=[("checkpoint", range(self.gen_params.checkpoint_count))])

        @def_method(m, allocate_checkpoint, ready=~checkpoints_full)
        def _():
            m.d.sync += checkpoints_head.eq(next_checkpoint)
            m.d.sync += checkpoints_full.eq(checkpoints_next_tail_comb == next_checkpoint)
            m.d.comb += checkpoints_full_overwrite.eq(1)
            log.debug(m, True, "checkpoint allocated 0x{:x}", checkpoints_head)
            return checkpoints_head

        checkpointed_tags_set_mask = Signal.like(checkpointed_tags)

        def make_new_checkpoint(*, from_tag: Value):
            checkpoint = allocate_checkpoint(m)

            m.d.comb += checkpointed_tags_set_mask.eq(1 << from_tag)
            tag_map.write(m, addr=from_tag, data=checkpoint)

            return checkpoint

        # --------------------------------------
        # FRAT renaming and checkpoint creation
        # --------------------------------------

        create_checkpoint_pipe = Pipe([("checkpoint", range(self.gen_params.checkpoint_count))])

        @def_method(m, self.rename)
        def _(rp_dst: Value, rl_dst: Value, rl_s1: Value, rl_s2: Value, tag: Value, commit_checkpoint: Value):
            # don't overwrite freshly restored FRAT with flushed inactive instructions
            tag_valid = Signal()
            m.d.av_comb += tag_valid.eq(~frat_lock | (tag == frat_unlock_tag))
            with m.If(tag_valid):
                m.d.sync += frat_lock.eq(0)

            with condition(m, nonblocking=True) as cond:
                with cond(commit_checkpoint & tag_valid):
                    checkpoint_id = make_new_checkpoint(from_tag=tag).checkpoint
                    log.debug(m, True, "checkpoint created t 0x{:x} -> c 0x{:x}", tag, checkpoint_id)
                    # Checkpoints have to save frat state after instruction (ex. JALR writes rd), write to storage is
                    # done one cycle later by piped transaction.
                    # guarantee that it will be executed cycle later by allocating id now
                    create_checkpoint_pipe.write(m, checkpoint=checkpoint_id)
                    # Future optimization: If no change happened in FRAT, then checkpoint
                    # could be shared with multiple tags (useful for branch chains)

            with m.If(tag_valid & (rl_dst != 0)):
                m.d.sync += self.frat[rl_dst].eq(rp_dst)
                log.debug(m, True, "frat write for rl {} -> rp {}", rl_dst, rp_dst)

            log.debug(
                m,
                True,
                "frat rename r_s1: {} -> {} r_s2 {} -> {} tag 0x{:x} [{}] ({})",
                rl_s1,
                self.frat[rl_s1],
                rl_s2,
                self.frat[rl_s2],
                tag,
                frat_unlock_tag,
                tag_valid,
            )
            return {"rp_s1": self.frat[rl_s1], "rp_s2": self.frat[rl_s2]}

        with Transaction().body(m):
            checkpoint = create_checkpoint_pipe.read(m).checkpoint
            storage.write(m, addr=checkpoint, data=self.frat)

        # Block until last FRAT overwrite from Rollback is finished.
        # Retirement restores entries on hard-flushes that were not covered by checkpoints one-by-one, don't overwrite.
        @def_method(m, self.flush_restore, ready=last_rollback_finished)
        def _(rl_dst: Value, rp_dst: Value):
            with m.If(rl_dst != 0):  # Duplicated, because otherwise causes comb loop in rename condition
                m.d.sync += self.frat[rl_dst].eq(rp_dst)

        self.flush_restore.add_conflict(self.rename, Priority.RIGHT)
        # FIXME: Commented due to Transactron #63. rollback is not currently used, fix later
        # self.rollback.add_conflict(self.flush_restore, Priority.RIGHT)

        # -------------------------------------------
        # Instructon tagging and stalling before RAT
        # -------------------------------------------

        last_issued_tag = Signal(self.gen_params.tag_bits)
        next_tag_increment = Signal()

        frat_tag_in_next_cycle = Signal(self.gen_params.tag_bits)

        @def_method(m, self.tag)
        def _(rollback_tag: Value, rollback_tag_v: Value, commit_checkpoint: Value):
            instr_rollback_tag = rollback_tag
            rollback_target_valid = (instr_rollback_tag == rollback_target_tag) & rollback_tag_v
            rollback_frat_ready = (instr_rollback_tag == frat_tag_in_next_cycle) & rollback_tag_v

            out_tag = Signal(self.gen_params.tag_bits)
            out_commit_checkpoint = Signal()

            tag_increment_allocate = Signal()
            tag_allocation_set_active = Signal()
            stall = Signal()

            # tag is incremented:
            # * on next instruction after each branch (next speculation path validity point,
            # checkpoint will be attached to it on next branch).
            # * on first instruction after rollback (so mispeculated instructions from last tag and
            # without checkpoint made could be invalidated).

            with m.If(~rollback_just_started):
                # Normal instruction flow tagging operation - if commit_checkpoint is needed, allocate pending tags
                # and schedule new tag for next instruction
                m.d.av_comb += tag_increment_allocate.eq(next_tag_increment)
                m.d.av_comb += tag_allocation_set_active.eq(1)
                # branch instruction is the last one with the current tag (checkpoint is added to existing tag)
                m.d.sync += next_tag_increment.eq(commit_checkpoint)
                m.d.av_comb += out_commit_checkpoint.eq(commit_checkpoint)

            with m.Else():
                # In-rollback flow
                m.d.sync += next_tag_increment.eq(0)
                m.d.av_comb += out_commit_checkpoint.eq(0)

                with m.If(rollback_target_valid & ~rollback_frat_ready):
                    # FRAT is still not loaded with correct rollback checkpoint,
                    # and a valid instruction from newly fetched path is currently waiting
                    # (invalid instructions from scheduler were flushed).
                    m.d.av_comb += stall.eq(1)
                with m.Elif(rollback_target_valid & rollback_frat_ready):
                    # FRAT has correct checkpoint loaded (currently or in next cycle) and scheduler
                    # finished flushing. Resume normal operation.
                    m.d.av_comb += tag_increment_allocate.eq(1)
                    m.d.av_comb += tag_allocation_set_active.eq(1)
                    # There may be still invalid entries (from old speculation path/flushed), between `tag`
                    # and `rename` stages. Issue new tag, and set `rename` to unblock writes on it.
                    m.d.sync += frat_unlock_tag.eq(out_tag)
                    m.d.sync += rollback_just_started.eq(0)
                    m.d.sync += next_tag_increment.eq(commit_checkpoint)
                    m.d.av_comb += out_commit_checkpoint.eq(commit_checkpoint)
                with m.Else():
                    # Instructions from old speculation path that should be flushed. FRAT has writes locked,
                    # and tags are already marked as non-active.
                    m.d.av_comb += tag_increment_allocate.eq(next_tag_increment)
                    # Pending tag must be issed for checkpoint correctness, but is issued as non-active
                    m.d.av_comb += tag_allocation_set_active.eq(0)

            with condition(m) as cond:
                with cond(~stall & tag_increment_allocate):
                    m.d.comb += out_tag.eq(allocate_tag(m, active=tag_allocation_set_active))
                with cond(~stall & ~tag_increment_allocate):
                    m.d.comb += out_tag.eq(last_issued_tag)

            m.d.sync += last_issued_tag.eq(out_tag)

            return {"tag": out_tag, "tag_increment": tag_increment_allocate, "commit_checkpoint": out_commit_checkpoint}

        # --------------------------------------------
        # Rollback RAT restore memory access pipeline
        # --------------------------------------------

        rollback_tag_s1 = Signal(self.gen_params.tag_bits)
        rollback_tag_s2 = frat_tag_in_next_cycle

        active_tags_reset_mask_0 = Signal.like(active_tags, init=0)

        @def_method(m, self.rollback)
        def _(tag: Value):
            tag_map.read_req(m, addr=tag)
            m.d.sync += rollback_tag_s1.eq(tag)

            # Invalidate tags on wrong speculaton path (suffix), but don't free them for instruction validity tracking
            with m.If((tag + 1 == tags_tail)):
                log.debug(m, True, "rollback to 0x{:x}. no tags to invalidate", tag)
            with m.Else():
                invalidate_mask = cyclic_mask(2**self.gen_params.tag_bits, tag + 1, tags_tail - 1)
                m.d.comb += active_tags_reset_mask_0.eq(invalidate_mask)
                log.debug(
                    m, True, "rollback to 0x{:x}. invalidate tags from 0x{:x} to 0x{:x}", tag, tag + 1, tags_tail - 1
                )

            log.assertion(m, ((active_tags & checkpointed_tags) & (1 << tag)).any(), "rollback to illegal tag")
            log.assertion(m, ~self.dm.get_dependency(CoreStateKey())(m).flushing, "rollback during core hard flush")

            m.d.sync += rollback_target_tag.eq(tag)
            m.d.sync += last_rollback_finished.eq(0)
            m.d.sync += rollback_just_started.eq(1)

            m.d.sync += frat_lock.eq(1)
            m.d.sync += frat_unlock_tag.eq(1 << self.gen_params.tag_bits)  # lock to non-existent tag

        checkpointed_tags_reset_mask_0 = Signal.like(checkpointed_tags)
        with Transaction().body(m):
            rollback_checkpoint_id = tag_map.read_resp(m)

            # Delete suffix of used checkpoints on wrong speculation path, including currently
            # restored checkpoint that will no longer be used.
            m.d.sync += checkpoints_head.eq(rollback_checkpoint_id)
            m.d.sync += checkpoints_full.eq(0)
            # Rollback target tag still remains active, but without checkpoint
            m.d.comb += checkpointed_tags_reset_mask_0.eq(1 << rollback_target_tag)

            storage.read_req(m, addr=rollback_checkpoint_id)
            m.d.sync += rollback_tag_s2.eq(rollback_tag_s1)  # `CRAT.tag` unblock condition (= frat_tag_in_next_cycle)

        with Transaction().body(m):
            rollback_frat = storage.read_resp(m)
            m.d.sync += assign(self.frat, rollback_frat.data)  # (frat is locked)
            m.d.sync += last_rollback_finished.eq((rollback_target_tag == rollback_tag_s2) & ~self.rollback.run)
            log.debug(m, True, "frat restored to rollback tag 0x{:x}", rollback_tag_s2)

        # --------------
        # Retiring tags
        # --------------

        active_tags_reset_mask_1 = Signal.like(active_tags, init=0)
        checkpointed_tags_reset_mask_1 = Signal.like(checkpointed_tags)

        @def_method(m, self.free_tag)
        def _():
            # If we free a tag, it means that we have retired a next one (tag+1).
            # Tag is no longer referenced in core, so it can be freed.

            freed_tag = tags_tail

            m.d.comb += active_tags_reset_mask_1.eq(1 << freed_tag)
            m.d.sync += tags_tail.eq(freed_tag + 1)

            # deallocate physical checkpoints (but not tags) associated with freed tag
            with m.If(((checkpointed_tags & active_tags) & (1 << freed_tag)).any()):
                m.d.comb += checkpoints_next_tail_comb.eq(mod_incr(checkpoints_tail, self.gen_params.checkpoint_count))
                m.d.sync += checkpoints_tail.eq(checkpoints_next_tail_comb)
                with m.If(~checkpoints_full_overwrite):
                    m.d.sync += checkpoints_full.eq(0)

                log.debug(m, True, "freed checkpoint 0x{:x}", checkpoints_tail)

            m.d.comb += checkpointed_tags_reset_mask_1.eq(1 << freed_tag)

            log.debug(m, True, "freed tag 0x{:x}", freed_tag)
            log.assertion(m, (tags_tail + 1) != tags_head, "tag free underflow")

        # -----
        # Misc
        # -----

        @def_method(m, self.get_active_tags, nonexclusive=True)
        def _():
            out = Signal(ArrayLayout(1, 2**self.gen_params.tag_bits))
            m.d.av_comb += out.eq(active_tags)
            return {"active_tags": out}

        m.submodules.perf_tags = perf_tags = HwExpHistogram(
            "struct.crat.tags_allocated",
            description="Number of allocated (virtual checkpoint) tags",
            bucket_count=self.gen_params.tag_bits + 1,
            sample_width=self.gen_params.tag_bits + 1,
        )
        m.submodules.perf_tags_active = perf_tags_active = HwExpHistogram(
            "struct.crat.tags_active",
            description="Number of tags that are currently active (on valid speculation path)",
            bucket_count=self.gen_params.tag_bits + 1,
            sample_width=self.gen_params.tag_bits + 1,
        )
        m.submodules.perf_checkpoints = perf_checkpoints = HwExpHistogram(
            "struct.crat.checkpoints_allocated",
            description="Number of allocated physical checkpoints",
            bucket_count=ceil_log2(self.gen_params.checkpoint_count),
            sample_width=ceil_log2(self.gen_params.checkpoint_count),
        )
        if perf_tags.metrics_enabled():
            with Transaction().body(m):
                num_tags = Signal(self.gen_params.tag_bits + 1)
                m.d.comb += num_tags.eq(
                    Mux(
                        tags_tail < tags_head,
                        tags_head - tags_tail,
                        2**self.gen_params.tag_bits - tags_tail + tags_head,
                    )
                )
                perf_tags.add(m, num_tags)
        if perf_tags_active.metrics_enabled():
            with Transaction().body(m):
                perf_tags_active.add(m, popcount(active_tags))
        if perf_checkpoints.metrics_enabled():
            with Transaction().body(m):
                num_checkpoints = Signal(range(self.gen_params.checkpoint_count))
                m.d.comb += num_checkpoints.eq(
                    Mux(
                        (checkpoints_tail < checkpoints_head)
                        | ((checkpoints_tail == checkpoints_head) & ~checkpoints_full),
                        checkpoints_head - checkpoints_tail,
                        self.gen_params.checkpoint_count - checkpoints_tail + checkpoints_head,
                    )
                )
                perf_checkpoints.add(m, num_checkpoints)

        active_tags_reset_mask = active_tags_reset_mask_0 | active_tags_reset_mask_1
        checkpointed_tags_reset_mask = checkpointed_tags_reset_mask_0 | checkpointed_tags_reset_mask_1
        m.d.sync += active_tags.eq((active_tags | active_tags_set_mask) & ~active_tags_reset_mask)
        m.d.sync += checkpointed_tags.eq(
            (checkpointed_tags | checkpointed_tags_set_mask) & ~checkpointed_tags_reset_mask
        )

        m.submodules.storage = storage
        m.submodules.tag_map = tag_map
        m.submodules.create_checkpoint_pipe = create_checkpoint_pipe

        return m
