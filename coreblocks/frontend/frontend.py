from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Connect, Pipe
from transactron.utils import assign
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch.optypes import OpType
from coreblocks.params.genparams import GenParams
from coreblocks.frontend import FrontendParams
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.frontend.stall_controller import StallController
from coreblocks.cache.icache import ICache, ICacheBypass
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import BranchVerifyKey, FlushICacheKey, PredictedJumpTargetKey, RollbackKey
from coreblocks.peripherals.bus_adapter import BusMasterInterface


class RollbackTagger(Elaboratable):
    """
    Provides `rollback_tag` field for instructions leaving the `Frontend` and decides on which instructions
    a checkpoint should be created.

    `rollback_tag` is used to identify new instructions fetched after each rollback.
    Instructions from previous rollback are flushed internally in `Frontend` (and this module),
    but this is needed to differentiate from instructions that left `Frontend` earlier.

    Requires `get_instr` and `push_instr` methods
    """

    get_instr: Required[Method]
    push_instr: Required[Method]
    rollback: Provided[Method]

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params

        self.get_instr = Method(o=gen_params.get(DecodeLayouts).decode_result)
        self.push_instr = Method(i=gen_params.get(DecodeLayouts).tagged_decode_result)

        self.rollback = Method(i=gen_params.get(RATLayouts).rollback_in)
        DependencyContext.get().add_dependency(RollbackKey(), self.rollback)

    def elaborate(self, platform):
        m = TModule()

        rollback_tag = Signal(self.gen_params.tag_bits)
        rollback_tag_v = Signal()

        with Transaction().body(m):
            instrs = self.get_instr(m)

            out = Signal(self.gen_params.get(DecodeLayouts).tagged_decode_result)
            m.d.av_comb += assign(out, instrs)
            # TODO: as branch is always the first insn, these should be per group
            for i in range(self.gen_params.frontend_superscalarity):
                # fetcher guarantees that if branch is present, it's the last insn
                # but computing this for each insn is simpler
                is_branch = instrs.data[i].exec_fn.op_type == OpType.BRANCH
                # no need to make checkpoint at JALR, we currently stall the fetch on it

                m.d.av_comb += out.data[i].rollback_tag.eq(rollback_tag)
                m.d.av_comb += out.data[i].rollback_tag_v.eq(rollback_tag_v)
                m.d.av_comb += out.data[i].commit_checkpoint.eq(is_branch)

            m.d.sync += rollback_tag_v.eq(0)

            self.push_instr(m, out)

        @def_method(m, self.rollback)
        def _(tag: Value):
            m.d.sync += rollback_tag.eq(tag)
            m.d.sync += rollback_tag_v.eq(1)

        return m


class FetchAddressUnit(Elaboratable):
    """
    This module owns the speculative fetch program counter and arbitrates all frontend redirects.
    It selects the next fetch PC based on reset, backend redirects, IFU redirects, and branch prediction results.
    """

    read: Provided[Method]
    ifu_redirect: Provided[Method]
    beckend_redirect: Provided[Method]

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        layouts = self.gen_params.get(FetchLayouts)

        self.read = Method(o=layouts.fetch_request)
        self.ifu_redirect = Method(i=layouts.redirect)
        self.backend_redirect = Method(i=layouts.redirect)

    def elaborate(self, platform):
        m = TModule()

        front_params = self.gen_params.get(FrontendParams)

        next_fetch_pc = Signal(self.gen_params.isa.xlen, init=self.gen_params.start_pc)

        @def_method(m, self.read)
        def _():
            # No branch prediction yet - just fallthrough to the next fetch block.
            m.d.sync += next_fetch_pc.eq(front_params.pc_from_fb(front_params.fb_addr(next_fetch_pc) + 1, 0))
            return next_fetch_pc

        @def_method(m, self.ifu_redirect)
        def _(pc):
            m.d.sync += next_fetch_pc.eq(pc)

        @def_method(m, self.backend_redirect)
        def _(pc):
            m.d.sync += next_fetch_pc.eq(pc)

        return m


class CoreFrontend(Elaboratable):
    """Frontend of the core."""

    consume_instr: Provided[Method]
    """Consume a single decoded instruction."""

    resume_from_exception: Provided[Method]
    """Resume the frontend from the given PC after an exception."""

    stall: Provided[Method]
    """Stall and flush the frontend."""

    def __init__(self, *, gen_params: GenParams, instr_bus: BusMasterInterface):
        self.gen_params = gen_params
        self.connections = DependencyContext.get()

        self.instr_buffer = BasicFifo(self.gen_params.get(FetchLayouts).fetch_result, self.gen_params.instr_buffer_size)

        cache_layouts = self.gen_params.get(ICacheLayouts)
        if gen_params.icache_params.enable:
            self.icache_refiller = SimpleCommonBusCacheRefiller(cache_layouts, self.gen_params.icache_params, instr_bus)
            self.icache = ICache(cache_layouts, self.gen_params.icache_params, self.icache_refiller)
        else:
            self.icache = ICacheBypass(cache_layouts, gen_params.icache_params, instr_bus)

        self.connections.add_dependency(FlushICacheKey(), self.icache.flush)

        self.stall_ctrl = StallController(self.gen_params)

        self.fetch_address_unit = FetchAddressUnit(self.gen_params)
        self.fetch_writeback = Method(i=gen_params.get(FetchLayouts).fetch_writeback)

        self.fetch = FetchUnit(self.gen_params, self.icache)
        self.fetch.cont.provide(self.instr_buffer.write)
        self.fetch.stall_unsafe.provide(self.stall_ctrl.stall_unsafe)

        # TODO: change back to Pipe after Scheduler made superscalar
        self.output_pipe = Pipe(self.gen_params.get(SchedulerLayouts).scheduler_in)
        self.decode_buff = Connect(self.gen_params.get(DecodeLayouts).decode_result)

        # TODO: move and implement these methods
        jb_layouts = self.gen_params.get(JumpBranchLayouts)
        self.target_pred_req = Method(i=jb_layouts.predicted_jump_target_req)
        self.target_pred_resp = Method(o=jb_layouts.predicted_jump_target_resp)
        DependencyContext.get().add_dependency(PredictedJumpTargetKey(), (self.target_pred_req, self.target_pred_resp))

        self.consume_instr = Method(o=self.gen_params.get(SchedulerLayouts).scheduler_in)
        self.resume_from_exception = self.stall_ctrl.resume_from_exception
        self.stall = Method()

        self.rollback_tagger = RollbackTagger(self.gen_params)

    def elaborate(self, platform):
        m = TModule()

        if self.gen_params.icache_params.enable:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch_address_unit = self.fetch_address_unit
        m.submodules.fetch = self.fetch
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.decode = decode = DecodeStage(gen_params=self.gen_params)
        decode.get_raw.provide(self.instr_buffer.read)
        decode.push_decoded.provide(self.decode_buff.write)

        m.submodules.decode_buff = self.decode_buff

        m.submodules.rollback_tagger = rollback_tagger = self.rollback_tagger
        rollback_tagger.get_instr.provide(self.decode_buff.read)
        rollback_tagger.push_instr.provide(self.output_pipe.write)
        self.consume_instr.provide(self.output_pipe.read)

        m.submodules.output_pipe = self.output_pipe

        m.submodules.stall_ctrl = self.stall_ctrl
        self.stall_ctrl.redirect_frontend.provide(self.fetch_address_unit.backend_redirect)
        self.fetch.fetch_writeback.provide(self.fetch_writeback)

        # TODO: Remove when Branch Predictor implemented
        with Transaction(name="DiscardBranchVerify").body(m):
            read = self.connections.get_dependency(BranchVerifyKey())
            read(m)  # Consume to not block JB Unit

        @def_method(m, self.target_pred_req)
        def _():
            pass

        @def_method(m, self.target_pred_resp)
        def _(arg):
            return {"valid": 0, "cfi_target": 0}

        @def_method(m, self.fetch_writeback)
        def _(redirect, redirect_target):
            with m.If(redirect):
                self.fetch_address_unit.ifu_redirect(m, pc=redirect_target)

        with Transaction(name="FetchRequest").body(m):
            self.stall_ctrl.stall_guard(m)
            self.fetch.fetch_request(m, self.fetch_address_unit.read(m))

        def flush_frontend():
            self.fetch.flush(m)
            self.instr_buffer.clear(m)
            self.output_pipe.clear(m)

        @def_method(m, self.stall)
        def _():
            flush_frontend()
            self.stall_ctrl.stall_exception(m)

        return m
