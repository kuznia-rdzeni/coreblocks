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
from coreblocks.frontend.bpu.ras import RAS
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
    bpu_update: Required[Method]
    """Train the branch predictor with a resolved branch."""

    ifu_writeback: Provided[Method]
    """
    Handle an IFU-detected misprediction/unsafe instruction: flush the BPU and optionally
    redirect fetch to a new PC.
    """
    bpu_response: Provided[Method]
    """Accept a branch prediction result and supply the predicted next PC to the FAU."""
    read_prediction: Provided[Method]
    """Return the branch prediction stored for a given FTQ entry (read by the fetch unit)."""

    check_stale: Provided[Methods]
    drain: Provided[Method]
    ras_peek: Provided[Method]
    ras_predict: Provided[Method]

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
        self.bpu_update = Method(i=bpu_layouts.update)
        self.read_prediction = Method(i=ifu_layouts.read_prediction_req, o=ifu_layouts.bpu_prediction)
        self.check_stale = Methods(2, i=ifu_layouts.check_stale_req, o=ifu_layouts.check_stale_resp)
        self.drain = Method()

        self.ras_peek = Method(o=ifu_layouts.ras_top)
        self.ras_predict = Method(i=ifu_layouts.ras_predict)

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
        fetch_layouts = self.gen_params.get(FetchLayouts)

        m.submodules.fetch_address_unit = fetch_address_unit = FetchAddressUnit(self.gen_params)

        m.submodules.pc_mem = pc_mem = FTQMemoryWrapper(gen_params=self.gen_params, layout=make_layout(fields.pc))
        m.submodules.jb_unit_prediction_mem = jb_unit_prediction_mem = MemoryBank(
            shape=self.jump_target_resp.data_out.shape(), depth=self.gen_params.ftq_size
        )

        prediction_mem = Array(
            Signal(fetch_layouts.bpu_prediction, name=f"prediction_{i}") for i in range(self.gen_params.ftq_size)
        )

        train_layout = make_layout(
            ("valid", 1), fields.pc, fields.cfi_target, fields.cfi_idx, fields.cfi_type, ("taken", 1)
        )
        train_mem = Array(Signal(train_layout, name=f"train_{i}") for i in range(self.gen_params.ftq_size))

        m.submodules.ras = ras = RAS(self.gen_params)
        ras_ckpt = Array(Signal(ras.state_layout, name=f"ras_ckpt_{i}") for i in range(self.gen_params.ftq_size))

        # Three pointers in the queue.
        alloc_ptr = FTQPtr(gen_params=self.gen_params)
        fetch_ptr = FTQPtr(gen_params=self.gen_params)
        commit_ptr = FTQPtr(gen_params=self.gen_params)

        entry_gen = Array(
            Signal(make_layout(fields.fetch_gen).size, name=f"entry_gen_{i}") for i in range(self.gen_params.ftq_size)
        )
        draining = Signal()

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
            m.d.sync += prediction_mem[alloc_ptr.ptr].eq(0)
            m.d.sync += train_mem[alloc_ptr.ptr].valid.eq(0)

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
        def _(pc, ftq_ptr, prediction):
            fetch_address_unit.write(m, pc=pc)
            m.d.sync += prediction_mem[ftq_ptr.ptr].eq(prediction)

        @def_method(m, self.read_prediction)
        def _(ftq_ptr):
            return prediction_mem[ftq_ptr.ptr]

        @def_methods(m, self.check_stale)
        def _(_, ftq_ptr, fetch_gen):
            p = FTQPtr(ftq_ptr, gen_params=self.gen_params)
            return {"stale": (entry_gen[p.ptr] != fetch_gen) | (p >= fetch_ptr) | draining}

        @def_method(m, self.drain)
        def _():
            m.d.sync += draining.eq(1)

        @def_method(m, self.ras_peek, nonexclusive=True)
        def _():
            return ras.peek(m)

        @def_method(m, self.ras_predict)
        def _(ftq_ptr, push, pop, addr):
            new_state = ras.update(m, push=push, pop=pop, addr=addr)
            m.d.sync += ras_ckpt[ftq_ptr.ptr].eq(new_state)

        @def_method(m, self.ifu_writeback)
        def _(
            ftq_ptr,
            fetch_gen,
            redirect,
            cfi_valid,
            cfi_idx,
            cfi_type,
            cfi_target,
        ):
            ftq_ptr_casted = FTQPtr(ftq_ptr, gen_params=self.gen_params)
            ftq_ptr_plus_one = FTQPtr(gen_params=self.gen_params)
            m.d.av_comb += ftq_ptr_plus_one.eq(ftq_ptr_casted + 1)

            log.assertion(
                m,
                (entry_gen[ftq_ptr_casted.ptr] == fetch_gen) & (ftq_ptr_casted < fetch_ptr) & ~draining,
                "a stale fetch block wrote back",
            )

            jb_unit_prediction_mem.write(
                m,
                addr=ftq_ptr.ptr,
                data={"valid": cfi_valid, "cfi_idx": cfi_idx, "cfi_type": cfi_type, "cfi_target": cfi_target},
            )

            evlog.emit(m, FTQRollback.hw(ftq_ptr=ftq_ptr_plus_one, cause="ifu_writeback"))

            with m.If(redirect):
                self.bpu_flush(m)
                m.d.sync += alloc_ptr.eq(ftq_ptr_plus_one)
                m.d.comb += fetch_ptr_next.eq(ftq_ptr_plus_one)

                with m.If(cfi_valid):
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

            record = train_mem[ftq_ptr.ptr]
            with m.If(record.valid):
                self.bpu_update(
                    m,
                    pc=record.pc,
                    cfi_target=record.cfi_target,
                    cfi_idx=record.cfi_idx,
                    cfi_type=record.cfi_type,
                    taken=record.taken,
                )

        @def_method(m, self.backend_redirect)
        def _(ftq_ptr, pc):
            ftq_ptr_plus_one = FTQPtr(gen_params=self.gen_params)
            m.d.av_comb += ftq_ptr_plus_one.eq(FTQPtr(ftq_ptr, gen_params=self.gen_params) + 1)

            fetch_address_unit.backend_redirect(m, pc=pc)

            m.d.sync += draining.eq(0)

            evlog.emit(m, FTQRollback.hw(ftq_ptr=ftq_ptr_plus_one, cause="backend_redirect"))
            m.d.sync += alloc_ptr.eq(ftq_ptr_plus_one)
            m.d.sync += fetch_ptr.eq(ftq_ptr_plus_one)

            committed_ras = ras_ckpt[commit_ptr.ptr]
            ras.recover(m, sp=committed_ras.sp, count=committed_ras.count, top=committed_ras.top)

        @def_method(m, self.jump_target_req)
        def _(ftq_ptr):
            jb_unit_prediction_mem.read_req(m, addr=ftq_ptr.ptr)

        @def_method(m, self.jump_target_resp)
        def _():
            return jb_unit_prediction_mem.read_resp(m).data

        @def_method(m, self.resolve)
        def _(ftq_ptr, from_pc, next_pc, taken, cfi_idx, cfi_type):
            record = train_mem[ftq_ptr.ptr]
            m.d.sync += [
                record.valid.eq(1),
                record.pc.eq(from_pc),
                record.cfi_target.eq(next_pc),
                record.cfi_idx.eq(cfi_idx),
                record.cfi_type.eq(cfi_type),
                record.taken.eq(taken),
            ]

        return m
