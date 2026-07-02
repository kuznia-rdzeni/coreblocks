from amaranth import *
from amaranth.lib.data import Layout
import amaranth.lib.memory as memory
from transactron import *
from transactron.evlog import EventSource
from transactron.utils import make_layout, DependencyContext
from transactron.utils import logging
from transactron.lib.metrics import *

from coreblocks.params import GenParams
from coreblocks.arch import *
from coreblocks.interface.layouts import (
    CommonLayoutFields,
    FetchLayouts,
    JumpBranchLayouts,
    BranchPredictionLayouts,
    FTQPtr,
    FetchTargetQueueLayouts,
)
from coreblocks.interface.keys import PredictedJumpTargetKey, BranchResolveKey, FTQCommitKey
from coreblocks.frontend.fetch_addr_unit import FetchAddressUnit
from coreblocks.telemetry import FetchRequest, FTQAlloc, FTQCommit, FTQRollback


log = logging.HardwareLogger("frontend.ftq")
evlog = EventSource("frontend.ftq")


class FTQMemoryWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams, layout: Layout):
        self.gen_params = gen_params
        self.layout = layout
        self.item_width = self.layout.as_shape().width

        fields = self.gen_params.get(CommonLayoutFields)

        self.write_layout = make_layout(fields.ftq_ptr, ("data", self.layout))

        self.read_ptr_next = FTQPtr(gen_params=self.gen_params)
        self.read_data = Signal(self.layout)

        self.write = Method(i=self.write_layout)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.mem = mem = memory.Memory(shape=self.layout.as_shape(), depth=self.gen_params.ftq_size, init=[])
        wrport = mem.write_port()
        rdport = mem.read_port(transparent_for=[wrport])

        m.d.comb += rdport.addr.eq(self.read_ptr_next)
        m.d.comb += self.read_data.eq(rdport.data)

        @def_method(m, self.write)
        def _(ftq_ptr, data):
            m.d.comb += wrport.addr.eq(ftq_ptr.ptr)
            m.d.comb += wrport.data.eq(data)
            m.d.comb += wrport.en.eq(1)

        return m


class FetchTargetQueue(Elaboratable):
    """
    Tracks speculative fetch targets in a circular buffer indexed by FTQ pointer.
    Each entry represents one fetch block: the FTQ allocates an entry per fetch, sends the PC to
    both the IFU and BPU, and advances the fetch pointer. Entries are freed at retirement via
    ``commit`` and the buffer stalls allocation when full.
    """

    stall_guard: Required[Method]
    """Blocks only while the pipeline is stalled (e.g. during a flush)."""
    ifu_request: Required[Method]
    """Issue a fetch request to the instruction fetch unit for the given PC and FTQ pointer."""
    bpu_request: Required[Method]
    """Request a branch prediction for the given PC and FTQ pointer."""
    bpu_flush: Required[Method]
    """Flush pending branch prediction requests (called on any redirect)."""

    ifu_writeback: Provided[Method]
    """
    Handle an IFU-detected misprediction/unsafe instruction: flush the BPU and optionally
    redirect fetch to a new PC.
    """
    bpu_response: Provided[Method]
    """Accept a branch prediction result and supply the predicted next PC to the FAU."""
    jump_target_req: Provided[Method]
    """Request the predicted jump target for a given FTQ entry (stub)."""
    jump_target_resp: Provided[Method]
    """Return the predicted jump target for a given FTQ entry (stub)."""
    commit: Provided[Method]
    """Retire an FTQ entry, advancing the commit pointer and freeing the slot."""
    resolve: Provided[Method]
    """Record branch resolution information for a committed FTQ entry (stub)."""
    backend_redirect: Provided[Method]
    """Handle a backend misprediction: reset alloc/fetch pointers to commit+1 and redirect the FAU."""

    def __init__(
        self,
        gen_params: GenParams,
    ) -> None:
        self.gen_params = gen_params

        self.dep_manager = DependencyContext.get()

        self.stall_guard = Method()

        ifu_layouts = self.gen_params.get(FetchLayouts)
        self.ifu_request = Method(i=ifu_layouts.fetch_request)
        self.ifu_writeback = Method(i=ifu_layouts.fetch_writeback)

        bpu_layouts = self.gen_params.get(BranchPredictionLayouts)
        self.bpu_request = Method(i=bpu_layouts.request)
        self.bpu_response = Method(i=bpu_layouts.write_prediction)
        self.bpu_flush = Method()

        jb_layouts = self.gen_params.get(JumpBranchLayouts)
        self.jump_target_req = Method(i=jb_layouts.predicted_jump_target_req)
        self.jump_target_resp = Method(o=jb_layouts.predicted_jump_target_resp)
        self.dep_manager.add_dependency(PredictedJumpTargetKey(), (self.jump_target_req, self.jump_target_resp))

        ftq_layouts = self.gen_params.get(FetchTargetQueueLayouts)
        self.commit = Method(i=ftq_layouts.commit)
        self.resolve = Method(i=ftq_layouts.branch_resolve)
        self.backend_redirect = Method(i=ifu_layouts.frontend_redirect)

        self.dep_manager.add_dependency(BranchResolveKey(), self.resolve)
        self.dep_manager.add_dependency(FTQCommitKey(), self.commit)

    def elaborate(self, platform):
        m = TModule()

        fields = self.gen_params.get(CommonLayoutFields)

        m.submodules.fetch_address_unit = fetch_address_unit = FetchAddressUnit(self.gen_params)

        m.submodules.pc_mem = pc_mem = FTQMemoryWrapper(gen_params=self.gen_params, layout=make_layout(fields.pc))

        # Three pointers in the queue.
        alloc_ptr = FTQPtr(gen_params=self.gen_params)
        fetch_ptr = FTQPtr(gen_params=self.gen_params)
        commit_ptr = FTQPtr(gen_params=self.gen_params)

        fetch_ptr_next = FTQPtr(gen_params=self.gen_params)
        m.d.sync += fetch_ptr.eq(fetch_ptr_next)
        m.d.comb += fetch_ptr_next.eq(fetch_ptr)
        m.d.comb += pc_mem.read_ptr_next.eq(fetch_ptr_next)

        # FTQ_Alloc takes the next speculative PC, allocates an FTQ entry, and sends
        # a request back to BPU
        alloc_fetch_bypass = Signal(make_layout(fields.pc))
        with Transaction(name="FTQ_Alloc").body(
            m, ready=~FTQPtr.queue_full(alloc_ptr, commit_ptr)
        ) as ftq_alloc_transaction:
            self.stall_guard(m)

            ret = fetch_address_unit.read(m)

            self.bpu_request(m, pc=ret.pc, ftq_ptr=alloc_ptr)
            pc_mem.write(m, ftq_ptr=alloc_ptr, data=ret.pc)

            evlog.emit(m, FTQAlloc.hw(ftq_ptr=alloc_ptr, pc=ret.pc))

            m.d.av_comb += alloc_fetch_bypass.eq(ret)
            m.d.sync += alloc_ptr.eq(alloc_ptr + 1)

        # FTQ_Send_Fetch_Requests follows fetch_ptr and sends requests to IFU. It has its data
        # bypassed from FTQ_Alloc.
        early_fetch = Signal()
        m.d.comb += early_fetch.eq((fetch_ptr == alloc_ptr) & ftq_alloc_transaction.run)
        with Transaction(name="FTQ_Send_Fetch_Requests").body(
            m, ready=early_fetch | (fetch_ptr < alloc_ptr)
        ) as send_fetch_req_transaction:
            self.stall_guard(m)

            fetch_pc = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += fetch_pc.eq(Mux(early_fetch, alloc_fetch_bypass, pc_mem.read_data))

            self.ifu_request(m, ftq_ptr=fetch_ptr, pc=fetch_pc)
            evlog.emit(m, FetchRequest.hw(ftq_ptr=fetch_ptr, pc=fetch_pc))
            m.d.comb += fetch_ptr_next.eq(fetch_ptr + 1)

        ftq_alloc_transaction.schedule_before(send_fetch_req_transaction)

        @def_method(m, self.bpu_response)
        def _(pc, ftq_ptr):
            fetch_address_unit.write(m, pc=pc)

        @def_method(m, self.ifu_writeback)
        def _(
            ftq_ptr,
            redirect,
            redirect_target,
        ):
            ftq_ptr_plus_one = FTQPtr(gen_params=self.gen_params)
            m.d.av_comb += ftq_ptr_plus_one.eq(FTQPtr(ftq_ptr, gen_params=self.gen_params) + 1)

            self.bpu_flush(m)

            evlog.emit(m, FTQRollback.hw(ftq_ptr=ftq_ptr_plus_one, cause="ifu_writeback"))

            m.d.sync += alloc_ptr.eq(ftq_ptr_plus_one)
            m.d.comb += fetch_ptr_next.eq(ftq_ptr_plus_one)

            with m.If(redirect):
                fetch_address_unit.ifu_redirect(m, pc=redirect_target)

        @def_method(m, self.commit)
        def _(ftq_ptr):
            ftq_ptr_casted = FTQPtr(ftq_ptr, gen_params=self.gen_params)
            # With superscalar retirement, multiple FTQ entries can be committed per cycle,
            # so only check that commit advances monotonically
            log.assertion(
                m,
                commit_ptr <= ftq_ptr_casted,
                "FTQ entry was retired out-of-order",
            )

            evlog.emit(m, FTQCommit.hw(ftq_ptr=ftq_ptr))

            m.d.sync += commit_ptr.eq(ftq_ptr)

        @def_method(m, self.backend_redirect)
        def _(pc, from_unsafe):
            commit_ptr_plus_one = FTQPtr(gen_params=self.gen_params)
            m.d.av_comb += commit_ptr_plus_one.eq(FTQPtr(commit_ptr, gen_params=self.gen_params) + 1)

            fetch_address_unit.backend_redirect(m, pc=pc)

            # An unsafe instruction (e.g. a CSR access) is not squashed - it keeps its FTQ entry
            # and is committed normally. Its resume is signalled before it retires, so `commit_ptr`
            # is stale here and must not be used. The alloc/fetch pointers were already rewound to
            # just past the unsafe instruction when the fetch unit wrote it back (`ifu_writeback`).
            # For an exception/backend redirect the whole pipeline is squashed, so we restart
            # allocation right after the last committed entry.
            with m.If(~from_unsafe):
                evlog.emit(m, FTQRollback.hw(ftq_ptr=commit_ptr_plus_one, cause="backend_redirect"))
                m.d.sync += alloc_ptr.eq(commit_ptr_plus_one)
                m.d.sync += fetch_ptr.eq(commit_ptr_plus_one)

        @def_method(m, self.jump_target_req)
        def _():
            pass

        @def_method(m, self.jump_target_resp)
        def _(arg):
            return {"valid": 0, "cfi_target": 0}

        @def_method(m, self.resolve)
        def _(from_pc, next_pc, misprediction):
            pass

        return m
