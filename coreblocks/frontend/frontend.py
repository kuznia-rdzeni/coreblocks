from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Connect, Pipe
from transactron.utils import assign
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch.optypes import OpType
from coreblocks.params.genparams import GenParams
from coreblocks.frontend.ftq import FetchTargetQueue
from coreblocks.frontend.decoder.decode_stage import DecodeStage
from coreblocks.frontend.fetch.fetch import FetchUnit
from coreblocks.frontend.stall_controller import StallController
from coreblocks.frontend.bpu.bpu import BranchPredictionUnit
from coreblocks.cache.icache import ICache, ICacheBypass
from coreblocks.cache.refiller import SimpleCommonBusCacheRefiller
from coreblocks.interface.layouts import *
from coreblocks.interface.keys import FlushICacheKey, RollbackKey
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

        self.get_instr = Method(o=gen_params.get(DecodeLayouts).decoded_instr)
        self.push_instr = Method(i=gen_params.get(SchedulerLayouts).scheduler_in)

        self.rollback = Method(i=gen_params.get(RATLayouts).rollback_in)
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

        self.instr_buffer = BasicFifo(self.gen_params.get(FetchLayouts).raw_instr, self.gen_params.instr_buffer_size)

        cache_layouts = self.gen_params.get(ICacheLayouts)
        if gen_params.icache_params.enable:
            self.icache_refiller = SimpleCommonBusCacheRefiller(cache_layouts, self.gen_params.icache_params, instr_bus)
            self.icache = ICache(cache_layouts, self.gen_params.icache_params, self.icache_refiller)
        else:
            self.icache = ICacheBypass(cache_layouts, gen_params.icache_params, instr_bus)

        self.connections.add_dependency(FlushICacheKey(), self.icache.flush)

        self.stall_ctrl = StallController(self.gen_params)

        self.fetch = FetchUnit(self.gen_params, self.icache)
        self.fetch.cont.provide(self.instr_buffer.write)
        self.fetch.stall_unsafe.provide(self.stall_ctrl.stall_unsafe)

        self.output_pipe = Pipe(self.gen_params.get(SchedulerLayouts).scheduler_in)
        self.decode_buff = Connect(self.gen_params.get(DecodeLayouts).decoded_instr)

        self.bpu = BranchPredictionUnit(self.gen_params)
        self.ftq = FetchTargetQueue(self.gen_params)

        self.consume_instr = self.output_pipe.read
        self.resume_from_exception = self.stall_ctrl.resume_from_exception
        self.stall = Method()

        self.rollback_tagger = RollbackTagger(self.gen_params)

    def elaborate(self, platform):
        m = TModule()

        if self.gen_params.icache_params.enable:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch = self.fetch
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.ftq = self.ftq
        m.submodules.bpu = self.bpu

        self.ftq.bpu_request.provide(self.bpu.request)
        self.ftq.bpu_flush.provide(self.bpu.flush)
        self.ftq.stall_lock.provide(self.stall_ctrl.stall_guard)
        self.bpu.write_prediction.provide(self.ftq.bpu_response)

        self.ftq.ifu_request.provide(self.fetch.fetch_request)
        self.fetch.fetch_writeback.provide(self.ftq.ifu_redirect)
        self.stall_ctrl.redirect_frontend.provide(self.ftq.backend_redirect)

        m.submodules.decode = decode = DecodeStage(gen_params=self.gen_params)
        decode.get_raw.provide(self.instr_buffer.read)
        decode.push_decoded.provide(self.decode_buff.write)

        m.submodules.decode_buff = self.decode_buff

        m.submodules.rollback_tagger = rollback_tagger = self.rollback_tagger
        rollback_tagger.get_instr.provide(self.decode_buff.read)
        rollback_tagger.push_instr.provide(self.output_pipe.write)

        m.submodules.output_pipe = self.output_pipe

        m.submodules.stall_ctrl = self.stall_ctrl

        @def_method(m, self.stall)
        def _():
            self.fetch.flush(m)
            self.instr_buffer.clear(m)
            self.output_pipe.clear(m)
            self.bpu.flush(m)
            self.stall_ctrl.stall_exception(m)

        return m
