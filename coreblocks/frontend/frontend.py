from amaranth import *

from transactron.core import *
from transactron.lib import BasicFifo, Connect, Pipe
from transactron.utils import assign
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch.optypes import OpType
from coreblocks.interface.layouts import ExceptionInformationRegisterLayouts
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


class CoreFrontend(Elaboratable):
    """Frontend of the core."""

    consume_instr: Provided[Method]
    """Consume a single decoded instruction."""

    redirect: Provided[Method]
    """Redirect the frontend to a new PC."""

    flush: Provided[Method]

    get_exception_information: Required[Method]

    def __init__(self, *, gen_params: GenParams, instr_bus: BusMasterInterface):
        self.gen_params = gen_params
        self.connections = DependencyContext.get()

        layouts = self.gen_params.get(FetchLayouts)

        self.instr_buffer = BasicFifo(layouts.fetch_result, self.gen_params.instr_buffer_size)

        cache_layouts = self.gen_params.get(ICacheLayouts)
        if gen_params.icache_params.enable:
            self.icache_refiller = SimpleCommonBusCacheRefiller(cache_layouts, self.gen_params.icache_params, instr_bus)
            self.icache = ICache(cache_layouts, self.gen_params.icache_params, self.icache_refiller)
        else:
            self.icache = ICacheBypass(cache_layouts, gen_params.icache_params, instr_bus)

        self.connections.add_dependency(FlushICacheKey(), self.icache.flush)

        self.stall_ctrl = StallController(self.gen_params)

        self.fetch = FetchUnit(self.gen_params, self.icache)

        # TODO: change back to Pipe after Scheduler made superscalar
        self.output_pipe = Pipe(self.gen_params.get(SchedulerLayouts).scheduler_in)
        self.decode_buff = Connect(self.gen_params.get(DecodeLayouts).decode_result)

        self.bpu = BranchPredictionUnit(self.gen_params)
        self.ftq = FetchTargetQueue(self.gen_params)

        self.rollback_tagger = RollbackTagger(self.gen_params)

        self.consume_instr = Method(o=self.gen_params.get(SchedulerLayouts).scheduler_in)
        self.redirect = Method(i=layouts.backend_redirect)
        self.flush = Method()

        self.get_exception_information = Method(o=gen_params.get(ExceptionInformationRegisterLayouts).get)

    def elaborate(self, platform):
        m = TModule()

        if self.gen_params.icache_params.enable:
            m.submodules.icache_refiller = self.icache_refiller
        m.submodules.icache = self.icache

        m.submodules.fetch = self.fetch
        self.fetch.cont.provide(self.instr_buffer.write)
        self.fetch.stall_unsafe.provide(self.stall_ctrl.stall_unsafe)
        m.submodules.instr_buffer = self.instr_buffer

        m.submodules.ftq = self.ftq
        m.submodules.bpu = self.bpu

        self.ftq.bpu_request.provide(self.bpu.request)
        self.ftq.bpu_flush.provide(self.bpu.flush)
        self.ftq.stall_guard.provide(self.stall_ctrl.stall_guard)
        self.bpu.write_prediction.provide(self.ftq.bpu_response)

        self.ftq.ifu_request.provide(self.fetch.fetch_request)
        self.fetch.fetch_writeback.provide(self.ftq.ifu_writeback)

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
        self.stall_ctrl.redirect_frontend.provide(self.redirect)
        self.stall_ctrl.get_exception_information.provide(self.get_exception_information)

        @def_method(m, self.redirect)
        def _(ftq_ptr, pc):
            self.flush(m)
            self.ftq.backend_redirect(m, ftq_ptr=ftq_ptr, pc=pc)
            self.stall_ctrl.on_redirect_frontend(m)

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            self.fetch.flush(m)
            self.instr_buffer.clear(m)
            self.output_pipe.clear(m)

        return m
