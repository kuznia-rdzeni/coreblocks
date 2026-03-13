from amaranth import *
from amaranth.lib.data import Layout
import amaranth.lib.memory as memory
from transactron import *
from transactron.utils import make_layout, DependencyContext
from transactron.lib import logging
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
from coreblocks.interface.keys import PredictedJumpTargetKey, BranchResolveKey, FTQCommitEntry

log = logging.HardwareLogger("frontend.ftq")


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
        fields = self.gen_params.get(CommonLayoutFields)

        self.write = Method(i=make_layout(fields.pc))
        self.read = Method(o=layouts.fetch_request)
        self.ifu_redirect = Method(i=layouts.redirect)
        self.backend_redirect = Method(i=layouts.redirect)

    def elaborate(self, platform):
        m = TModule()

        next_fetch_addr = Signal(self.gen_params.isa.xlen, init=self.gen_params.start_pc)
        next_fetch_addr_v = Signal(init=1)

        next_fetch_addr_fwd = Signal.like(self.read.data_out)

        self.write.schedule_before(self.read)  # to avoid combinational loops

        @def_method(m, self.write, ready=~next_fetch_addr_v)
        def _(pc):
            m.d.av_comb += next_fetch_addr_fwd.eq(pc)
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        with m.If(next_fetch_addr_v):
            m.d.av_comb += next_fetch_addr_fwd.eq(next_fetch_addr)  # write method is not ready

        @def_method(m, self.read, ready=next_fetch_addr_v | self.write.run)
        def _():
            m.d.sync += next_fetch_addr_v.eq(0)
            return next_fetch_addr_fwd

        @def_method(m, self.ifu_redirect)
        def _(pc):
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        @def_method(m, self.backend_redirect)
        def _(pc):
            m.d.sync += next_fetch_addr.eq(pc)
            m.d.sync += next_fetch_addr_v.eq(1)

        return m


class FTQMemoryWrapper(Elaboratable):
    def __init__(self, gen_params: GenParams, layout: Layout):
        self.gen_params = gen_params
        self.layout = layout
        self.item_width = self.layout.as_shape().width

        fields = self.gen_params.get(CommonLayoutFields)

        self.write_layout = make_layout(fields.ftq_ptr, ("data", self.layout))

        self.read_ptr_next = FTQPtr(gp=self.gen_params)
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
    def __init__(
        self,
        gen_params: GenParams,
    ) -> None:
        self.gen_params = gen_params

        self.dep_manager = DependencyContext.get()

        self.stall_lock = Method()

        ifu_layouts = self.gen_params.get(FetchLayouts)
        self.ifu_request = Method(i=ifu_layouts.fetch_request)
        self.ifu_redirect = Method(i=ifu_layouts.fetch_writeback)

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
        self.backend_redirect = Method(i=ifu_layouts.redirect)

        self.dep_manager.add_dependency(BranchResolveKey(), self.resolve)
        self.dep_manager.add_dependency(FTQCommitEntry(), self.commit)

    def elaborate(self, platform):
        m = TModule()

        fields = self.gen_params.get(CommonLayoutFields)

        m.submodules.fetch_address_unit = fetch_address_unit = FetchAddressUnit(self.gen_params)

        m.submodules.pc_mem = pc_mem = FTQMemoryWrapper(gen_params=self.gen_params, layout=make_layout(fields.pc))

        alloc_ptr = FTQPtr(gp=self.gen_params)
        fetch_ptr = FTQPtr(gp=self.gen_params)
        commit_ptr = FTQPtr(gp=self.gen_params)

        fetch_ptr_next = FTQPtr(gp=self.gen_params)
        m.d.sync += fetch_ptr.eq(fetch_ptr_next)
        m.d.comb += fetch_ptr_next.eq(fetch_ptr)
        m.d.comb += pc_mem.read_ptr_next.eq(fetch_ptr_next)

        alloc_fetch_bypass = Signal(make_layout(fields.pc))
        with Transaction(name="FTQ_Alloc").body(
            m, ready=~FTQPtr.queue_full(alloc_ptr, commit_ptr)
        ) as ftq_alloc_transaction:
            self.stall_lock(m)

            ret = fetch_address_unit.read(m)

            log.debug(m, True, "[FTQ] Alloc pc={:x}, ftq={}", ret.pc, alloc_ptr.ptr)

            self.bpu_request(m, pc=ret.pc, ftq_ptr=alloc_ptr)
            pc_mem.write(m, ftq_ptr=alloc_ptr, data=ret.pc)

            m.d.av_comb += alloc_fetch_bypass.eq(ret)
            m.d.sync += alloc_ptr.eq(alloc_ptr + 1)

        early_fetch = Signal()
        m.d.comb += early_fetch.eq((fetch_ptr == alloc_ptr) & ftq_alloc_transaction.run)
        with Transaction(name="FTQ_Send_Fetch_Requests").body(
            m, ready=early_fetch | (fetch_ptr < alloc_ptr)
        ) as send_fetch_req_transaction:
            self.stall_lock(m)

            fetch_pc = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += fetch_pc.eq(Mux(early_fetch, alloc_fetch_bypass, pc_mem.read_data))

            log.debug(m, True, "[FTQ] IFU request pc={:x}, ftq={} early_fetch={}", fetch_pc, fetch_ptr.ptr, early_fetch)
            self.ifu_request(m, ftq_ptr=fetch_ptr, pc=fetch_pc)
            m.d.comb += fetch_ptr_next.eq(fetch_ptr + 1)

        ftq_alloc_transaction.schedule_before(send_fetch_req_transaction)

        @def_method(m, self.bpu_response)
        def _(pc, ftq_ptr):
            fetch_address_unit.write(m, pc=pc)

        @def_method(m, self.ifu_redirect)
        def _(
            ftq_ptr,
            redirect,
            redirect_target,
        ):
            ftq_ptr_plus_one = FTQPtr(gp=self.gen_params)
            m.d.av_comb += ftq_ptr_plus_one.eq(FTQPtr(ftq_ptr, gp=self.gen_params) + 1)

            self.bpu_flush(m)

            with m.If(redirect):
                fetch_address_unit.ifu_redirect(m, pc=redirect_target)
                m.d.sync += alloc_ptr.eq(ftq_ptr_plus_one)
                m.d.comb += fetch_ptr_next.eq(ftq_ptr_plus_one)

        @def_method(m, self.commit)
        def _(ftq_ptr):
            # We allow ftq_ptr to be 2 bigger than the commit ptr.
            # This can happen when we have a FTQ entry with 0 instructions
            # (an unaligned 4-byte long instruction crossing two fetch blocks).
            ftq_ptr_casted = FTQPtr(ftq_ptr, gp=self.gen_params)
            log.assertion(
                m,
                (commit_ptr <= ftq_ptr_casted) & (ftq_ptr_casted <= commit_ptr + 2),
                "FTQ entry was retired out-of-order",
            )

            log.debug(m, True, "[FTQ] Commit ftq={}", ftq_ptr.ptr)
            m.d.sync += commit_ptr.eq(ftq_ptr)

        @def_method(m, self.backend_redirect)
        def _(pc):
            commit_ptr_plus_one = FTQPtr(gp=self.gen_params)
            m.d.av_comb += commit_ptr_plus_one.eq(FTQPtr(commit_ptr, gp=self.gen_params) + 1)

            fetch_address_unit.backend_redirect(m, pc=pc)
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
