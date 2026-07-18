from amaranth import *
from amaranth.lib.data import Layout
import amaranth.lib.memory as memory
from transactron import *
from transactron.evlog import EventSource
from transactron.utils import make_layout, DependencyContext
from transactron.utils import logging
from transactron.lib.metrics import *
from transactron.lib.storage import MemoryBank

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
    check_stale: Provided[Methods]
    """
    Tell whether a fetch request (identified by its FTQ pointer and generation) is stale, i.e.
    was invalidated by a redirect after it was issued.
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
        self.check_stale = Methods(2, i=ifu_layouts.check_stale_req, o=ifu_layouts.check_stale_resp)

        jb_layouts = self.gen_params.get(JumpBranchLayouts)
        self.jump_target_req = Method(i=jb_layouts.predicted_jump_target_req)
        self.jump_target_resp = Method(o=jb_layouts.predicted_jump_target_resp)
        self.dep_manager.add_dependency(PredictedJumpTargetKey(), (self.jump_target_req, self.jump_target_resp))

        ftq_layouts = self.gen_params.get(FetchTargetQueueLayouts)
        self.commit = Method(i=ftq_layouts.commit)
        self.resolve = Method(i=ftq_layouts.branch_resolve)
        self.backend_redirect = Method(i=ifu_layouts.backend_redirect)

        self.dep_manager.add_dependency(BranchResolveKey(), self.resolve)
        self.dep_manager.add_dependency(FTQCommitKey(), self.commit)

    def elaborate(self, platform):
        m = TModule()

        fields = self.gen_params.get(CommonLayoutFields)

        m.submodules.fetch_address_unit = fetch_address_unit = FetchAddressUnit(self.gen_params)

        m.submodules.pc_mem = pc_mem = FTQMemoryWrapper(gen_params=self.gen_params, layout=make_layout(fields.pc))
        m.submodules.jb_unit_prediction_mem = jb_unit_prediction_mem = MemoryBank(
            shape=self.jump_target_resp.data_out.shape(), depth=self.gen_params.ftq_size
        )

        # Three pointers in the queue.
        alloc_ptr = FTQPtr(gen_params=self.gen_params)
        fetch_ptr = FTQPtr(gen_params=self.gen_params)
        commit_ptr = FTQPtr(gen_params=self.gen_params)

        entry_gen = Array(
            Signal(make_layout(fields.fetch_gen).size, name=f"entry_gen_{i}") for i in range(self.gen_params.ftq_size)
        )

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

            new_gen = entry_gen[fetch_ptr.ptr] + 1
            m.d.sync += entry_gen[fetch_ptr.ptr].eq(new_gen)

            self.ifu_request(m, ftq_ptr=fetch_ptr, pc=fetch_pc, fetch_gen=new_gen)
            m.d.comb += fetch_ptr_next.eq(fetch_ptr + 1)

            evlog.emit(m, FetchRequest.hw(ftq_ptr=fetch_ptr, pc=fetch_pc))

        ftq_alloc_transaction.schedule_before(send_fetch_req_transaction)

        @def_method(m, self.bpu_response)
        def _(pc, ftq_ptr):
            fetch_address_unit.write(m, pc=pc)

        # A request is stale iff any of:
        #  - its entry was re-issued since (generation mismatch),
        #  - its entry sits at or past the fetch pointer: a redirect rewound fetch over it and
        #    it was not re-issued yet,
        #  - the FTQ is stalled (pointers not rewound until the backend resumes).
        @def_methods(m, self.check_stale)
        def _(_, ftq_ptr, fetch_gen):
            p = FTQPtr(ftq_ptr, gen_params=self.gen_params)
            return {"stale": (entry_gen[p.ptr] != fetch_gen) | (p >= fetch_ptr) | (~self.stall_guard.ready)}

        @def_method(m, self.ifu_writeback)
        def _(
            ftq_ptr,
            redirect,
            stall,
            cfi_idx,
            cfi_type,
            cfi_target,
        ):
            ftq_ptr_plus_one = FTQPtr(gen_params=self.gen_params)
            m.d.av_comb += ftq_ptr_plus_one.eq(FTQPtr(ftq_ptr, gen_params=self.gen_params) + 1)

            # The record is valid only if fetch followed a taken CFI in this block. On a stall
            # (JALR with unknown target or fault/unsafe) no CFI was followed - the jump-branch
            # unit will detect the mispredict and the backend will redirect. A fall-through
            # resteer has cfi_type INVALID, so it never marks the record valid.
            jb_unit_prediction_mem.write(
                m,
                addr=ftq_ptr.ptr,
                data={
                    "valid": CfiType.valid(cfi_type) & ~stall,
                    "cfi_idx": cfi_idx,
                    "cfi_target": cfi_target,
                },
            )

            with m.If(redirect | stall):
                self.bpu_flush(m)
                m.d.sync += alloc_ptr.eq(ftq_ptr_plus_one)
                m.d.comb += fetch_ptr_next.eq(ftq_ptr_plus_one)

                evlog.emit(m, FTQRollback.hw(ftq_ptr=ftq_ptr_plus_one, cause="ifu_writeback"))

                with m.If(redirect):
                    fetch_address_unit.ifu_redirect(m, pc=cfi_target)

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
        def _(ftq_ptr, pc):
            ftq_ptr_plus_one = FTQPtr(gen_params=self.gen_params)
            m.d.av_comb += ftq_ptr_plus_one.eq(FTQPtr(ftq_ptr, gen_params=self.gen_params) + 1)

            fetch_address_unit.backend_redirect(m, pc=pc)

            evlog.emit(m, FTQRollback.hw(ftq_ptr=ftq_ptr_plus_one, cause="backend_redirect"))
            m.d.sync += alloc_ptr.eq(ftq_ptr_plus_one)
            m.d.sync += fetch_ptr.eq(ftq_ptr_plus_one)

        @def_method(m, self.jump_target_req)
        def _(ftq_ptr):
            jb_unit_prediction_mem.read_req(m, addr=ftq_ptr.ptr)

        @def_method(m, self.jump_target_resp)
        def _():
            return jb_unit_prediction_mem.read_resp(m).data

        @def_method(m, self.resolve)
        def _(from_pc, misprediction, taken, cfi_idx, cfi_type, cfi_target):
            pass

        return m
