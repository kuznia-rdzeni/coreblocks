from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Connect, Pipe
from transactron.utils import assign
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch.optypes import OpType
from coreblocks.params.genparams import GenParams
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
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
    """

    def __init__(self, *, get_instr: Method, push_instr: Method, gen_params: GenParams) -> None:
        self.gen_params = gen_params

        self.get_instr = get_instr
        self.push_instr = push_instr

        rat_layouts = gen_params.get(RATLayouts)
        self.rollback = Method(i=rat_layouts.rollback_in)
        DependencyContext.get().add_dependency(RollbackKey(), self.rollback)

    def elaborate(self, platform):
        m = TModule()

        rollback_tag = Signal(self.gen_params.tag_bits)
        rollback_tag_v = Signal()

        with Transaction().body(m):
            instr = self.get_instr(m)

            is_branch = instr.exec_fn.op_type == OpType.BRANCH
            # no need to make checkpoint at JALR, we currently stall the fetch on it

            out = Signal(self.gen_params.get(SchedulerLayouts).scheduler_in)
            m.d.av_comb += assign(out, instr)
            m.d.av_comb += out.rollback_tag.eq(rollback_tag)
            m.d.av_comb += out.rollback_tag_v.eq(rollback_tag_v)
            m.d.av_comb += out.commit_checkpoint.eq(is_branch)

            m.d.sync += rollback_tag_v.eq(0)

            self.push_instr(m, out)

        @def_method(m, self.rollback)
        def _(tag: Value):
            m.d.sync += rollback_tag.eq(tag)
            m.d.sync += rollback_tag_v.eq(1)

        return m


class CoreFrontend(Elaboratable):
    """Frontend of the core.

    Attributes
    ----------
    consume_instr: Method
        Consume a single decoded instruction.
    resume_from_exception: Method
        Resume the frontend from the given PC after an exception.
    resume_from_unsafe: Method
        Resume the frontend from the given PC after an unsafe instruction.
    stall: Method
        Stall and flush the frontend.
    """

    def __init__(self, *, gen_params: GenParams, instr_bus: BusMasterInterface):
        self.gen_params = gen_params
        self.connections = DependencyContext.get()

        self.instr_buffer = BasicFifo(self.gen_params.get(FetchLayouts).raw_instr, self.gen_params.instr_buffer_size)

        cache_layouts = self.gen_params.get(ICacheLayouts)
        if gen_params.icache_params.enable:
            self.icache_refiller = SimpleCommonBusCacheRefiller(cache_layouts, self.gen_params.icache_params, instr_bus)
            self.icache = ICache(cache_layouts, self.gen_params.icache_params, self.icache_refiller)
        else:
            self.icache = ICacheBypass(cache_layouts, gen_params.icache_params, instr_bus)

        self.connections.add_dependency(FlushICacheKey(), self.icache.flush)

        self.fetch = FetchUnit(self.gen_params, self.icache, self.instr_buffer.write)

        self.output_pipe = Pipe(self.gen_params.get(SchedulerLayouts).scheduler_in)
        self.decode_buff = Connect(self.gen_params.get(DecodeLayouts).decoded_instr)

        # TODO: move and implement these methods
        jb_layouts = self.gen_params.get(JumpBranchLayouts)
        self.target_pred_req = Method(i=jb_layouts.predicted_jump_target_req)
        self.target_pred_resp = Method(o=jb_layouts.predicted_jump_target_resp)
        DependencyContext.get().add_dependency(PredictedJumpTargetKey(), (self.target_pred_req, self.target_pred_resp))

        self.consume_instr = self.output_pipe.read
        self.resume_from_exception = self.fetch.resume_from_exception
        self.resume_from_unsafe = self.fetch.resume_from_unsafe
        self.stall = Method()

        self.rollback_tagger = RollbackTagger(
            gen_params=self.gen_params, get_instr=self.decode_buff.read, push_instr=self.output_pipe.write
        )

    def elaborate(self, platform):
        m = TModule()

        if self.gen_params.icache_params.enable:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch = self.fetch
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.decode = DecodeStage(
            gen_params=self.gen_params, get_raw=self.instr_buffer.read, push_decoded=self.decode_buff.write
        )
        m.submodules.decode_buff = self.decode_buff

        m.submodules.rollback_tagger = self.rollback_tagger
        m.submodules.output_pipe = self.output_pipe

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

        def flush_frontend():
            self.instr_buffer.clear(m)
            self.output_pipe.clean(m)

        @def_method(m, self.stall)
        def _():
            flush_frontend()
            self.fetch.stall_exception(m)

        return m
