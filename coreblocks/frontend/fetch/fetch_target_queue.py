from amaranth import *
from amaranth.lib.data import Layout
from collections.abc import Sequence

from transactron import *
from transactron.utils import make_layout, DependencyContext, assign, AssignArg, MethodStruct, popcount
from transactron.lib import logging, MemoryBank

from coreblocks.params import GenParams
from coreblocks.arch import *
from coreblocks.frontend import FrontendParams
from coreblocks.frontend.branch_prediction.iface import BranchPredictionUnitInterface
from coreblocks.interface.layouts import (
    CommonLayoutFields,
    FetchTargetQueueLayouts,
    JumpBranchLayouts,
    BranchPredictionLayouts,
    FTQPtr,
)
from coreblocks.interface.keys import PredictedJumpTargetKey, MispredictionReportKey, FetchResumeKey

log = logging.HardwareLogger("frontend.ftq")


class FetchTargetQueue(Elaboratable):
    def __init__(self, gen_params: GenParams, bpu: BranchPredictionUnitInterface) -> None:
        self.gen_params = gen_params
        self.bpu = bpu

        fields = self.gen_params.get(CommonLayoutFields)
        ftq_layouts = self.gen_params.get(FetchTargetQueueLayouts)

        self.consume_fetch_target = Method(o=ftq_layouts.consume_fetch_target)
        self.consume_prediction = Method(i=ftq_layouts.consume_prediction_i, o=ftq_layouts.consume_prediction_o)
        self.ifu_writeback = Method(i=ftq_layouts.ifu_writeback)

        # This must be called at least one cycle before the commit for the instruction that caused misprediction!
        self.report_misprediction = Method(i=ftq_layouts.report_misprediction)

        self.commit = Method(i=ftq_layouts.commit)

        self.stall = Method()
        self._on_resume = Method(i=make_layout(fields.pc, fields.ftq_idx, ("from_exception", 1)))

        self.stall_ctrl = StallController(self.gen_params, self._on_resume)

        jb_layouts = self.gen_params.get(JumpBranchLayouts)
        self.jump_target_req = Method(i=jb_layouts.predicted_jump_target_req)
        self.jump_target_resp = Method(o=jb_layouts.predicted_jump_target_resp)

        dm = DependencyContext.get()
        dm.add_dependency(PredictedJumpTargetKey(), (self.jump_target_req, self.jump_target_resp))
        dm.add_dependency(MispredictionReportKey(), self.report_misprediction)
        dm.add_dependency(FetchResumeKey(), self.stall_ctrl.resume)

    def elaborate(self, platform):
        m = TModule()

        fields = self.gen_params.get(CommonLayoutFields)

        m.submodules.stall_ctrl = self.stall_ctrl
        m.submodules.jump_target_mem = jump_target_mem = MemoryBank(
            data_layout=[fields.maybe_cfi_target], elem_count=self.gen_params.ftq_size, safe_writes=False
        )

        m.submodules.pc_queue = pc_queue = PCQueue(self.gen_params)
        m.submodules.prediction_queue = prediction_queue = PredictionDetailsQueue(self.gen_params)
        m.submodules.misprediction_reg = misprediction_reg = MispredictionInfoRegister(self.gen_params)

        # todo: pass the read pointer as an argument
        m.submodules.meta_mem = meta_mem = FTQMemoryWrapper(self.gen_params, make_layout(fields.bpu_meta))
        m.submodules.predecode_mem = predecode_mem = FTQMemoryWrapper(
            self.gen_params,
            make_layout(
                self.gen_params.get(BranchPredictionLayouts).block_prediction_field,
                fields.fb_addr,
                fields.fb_last_instr_idx,
                ("empty_block", 1),
            ),
        )

        commit_ptr = FTQPtr(gp=self.gen_params)
        commit_ptr_next = FTQPtr(gp=self.gen_params)
        m.d.sync += commit_ptr.eq(commit_ptr_next)
        m.d.comb += commit_ptr_next.eq(commit_ptr)

        m.d.comb += [
            meta_mem.read_ptr_next.eq(commit_ptr_next),
            predecode_mem.read_ptr_next.eq(commit_ptr_next),
        ]

        initalized = Signal()
        with Transaction(name="FTQ_Reset").body(m, request=~initalized):
            pc_queue.redirect(m, ftq_idx=FTQPtr(gp=self.gen_params), pc=self.gen_params.start_pc)
            m.d.sync += initalized.eq(1)

        with Transaction(name="FTQ_New_Prediction").body(m, request=initalized):
            self.stall_ctrl.stall_guard(m)
            self.bpu.request(m, pc_queue.bpu_consume(m))

        with Transaction(name="FTQ_Read_Target_Prediction").body(m):
            pred = self.bpu.read_target_pred(m)
            log.debug(
                m,
                True,
                "Predicted next PC=0x{:x}, FTQ={}/{}, bpu_stage={}",
                pred.pc,
                pred.ftq_idx.parity,
                pred.ftq_idx.ptr,
                pred.bpu_stage,
            )
            pc_queue.write(
                m,
                ftq_idx=FTQPtr(pred.ftq_idx, gp=self.gen_params) + 1,
                pc=pred.pc,
                bpu_stage=pred.bpu_stage,
                global_branch_history=pred.global_branch_history,
            )

        with Transaction(name="FTQ_Read_Prediction_Details").body(m):
            final_pred = self.bpu.read_pred_details(m)
            log.debug(
                m, True, "Writing prediction details for FTQ={}/{}", final_pred.ftq_idx.parity, final_pred.ftq_idx.ptr
            )
            prediction_queue.write(
                m,
                ftq_idx=final_pred.ftq_idx,
                bpu_stage=final_pred.bpu_stage,
                block_prediction=final_pred.block_prediction,
            )
            meta_mem.write(m, ftq_idx=final_pred.ftq_idx, data=final_pred.bpu_meta)

        @def_method(m, self.consume_fetch_target, ready=initalized)
        def _():
            self.stall_ctrl.stall_guard(m)
            return pc_queue.ifu_consume(m)

        self.consume_prediction.proxy(m, prediction_queue.try_consume)

        @def_method(m, self.ifu_writeback)
        def _(ftq_idx, fb_addr, fb_last_instr_idx, redirect, unsafe, block_prediction, empty_block):
            log.debug(m, True, "IFU writeback ftq={}/{}", ftq_idx.parity, ftq_idx.ptr)

            is_jalr_without_target = Signal()
            m.d.av_comb += is_jalr_without_target.eq(
                CfiType.is_jalr(block_prediction.cfi_type) & ~block_prediction.maybe_cfi_target.valid
            )

            with m.If(unsafe | (redirect & is_jalr_without_target)):
                self.stall_ctrl.stall_unsafe(m, ftq_idx=ftq_idx)

            with m.If(redirect & ~is_jalr_without_target):
                fallthrough_addr = self.gen_params.get(FrontendParams).pc_from_fb(fb_addr + 1, 0)
                redirect_pc = Mux(
                    CfiType.valid(block_prediction.cfi_type),
                    block_prediction.maybe_cfi_target.value,
                    fallthrough_addr,
                )
                pc_queue.redirect(m, ftq_idx=FTQPtr(ftq_idx, gp=self.gen_params) + 1, pc=redirect_pc)

            with m.If(redirect | unsafe):
                self.bpu.flush(m)

            predecode_mem.write(
                m,
                ftq_idx=ftq_idx,
                data={
                    "fb_addr": fb_addr,
                    "fb_last_instr_idx": fb_last_instr_idx,
                    "block_prediction": block_prediction,
                    "empty_block": empty_block,
                },
            )
            jump_target_mem.write(m, addr=ftq_idx.ptr, data={"maybe_cfi_target": block_prediction.maybe_cfi_target})

        self.report_misprediction.proxy(m, misprediction_reg.report_misprediction)

        commit_ready = Signal()
        if Extension.C in self.gen_params.isa.extensions:
            # TODO: instead of having a separate transaction and wasting one cycle every an empty block
            # we can simply make a new memory just with the `empty_block` bit, reading entry `commit_ptr + 1`
            # and advancing the commit pointer either by 1 or 2 depending on the emptiness bit.
            m.d.comb += commit_ready.eq(~predecode_mem.read_data.empty_block)
            with Transaction(name="FTQ_Empty_Block_Committer").body(m, request=predecode_mem.read_data.empty_block):
                log.debug(m, True, "Fetch block #{} is empty. Releasing the associated FTQ entry", commit_ptr.ptr)
                pc_queue.pop(m)
                m.d.comb += commit_ptr_next.eq(commit_ptr + 1)
        else:
            m.d.comb += commit_ready.eq(1)

        @def_method(m, self.commit, ready=commit_ready)
        def _(fb_instr_idx, exception):
            log.debug(m, True, "Committing instr #{} from FTQ={}/{}", fb_instr_idx, commit_ptr.parity, commit_ptr.ptr)
            predecode_data = predecode_mem.read_data

            with m.If(exception | (fb_instr_idx == predecode_data.fb_last_instr_idx)):
                meta_data = meta_mem.read_data
                prediction = predecode_data.block_prediction
                misprediction_data = misprediction_reg.get(
                    m, ftq_addr={"ftq_idx": commit_ptr, "fb_instr_idx": fb_instr_idx}
                )

                had_misprediction = misprediction_data.valid

                # TODO: comment about it
                cfi_type = Mux(
                    had_misprediction,
                    Mux(fb_instr_idx == prediction.cfi_idx, prediction.cfi_type, CfiType.BRANCH),
                    Mux(exception, CfiType.INVALID, prediction.cfi_type),
                )

                cfi_taken = ~CfiType.is_branch(cfi_type) | (had_misprediction ^ (fb_instr_idx == prediction.cfi_idx))

                self.bpu.update(
                    m,
                    fb_addr=predecode_data.fb_addr,
                    cfi_type=cfi_type,
                    cfi_idx=fb_instr_idx,
                    cfi_target=Mux(had_misprediction, misprediction_data.cfi_target, prediction.maybe_cfi_target.value),
                    cfi_taken=cfi_taken,
                    cfi_mispredicted=had_misprediction,
                    branch_mask=prediction.branch_mask & ((1 << (fb_instr_idx + 1)) - 1),  # trim the mask
                    global_branch_history=0,
                    bpu_meta=meta_data.bpu_meta,
                )

                log.debug(m, True, "Releasing FTQ entry #{}/{}", commit_ptr.parity, commit_ptr.ptr)
                pc_queue.pop(m)
                m.d.comb += commit_ptr_next.eq(commit_ptr + 1)

        @def_method(m, self.stall)
        def _():
            self.bpu.flush(m)
            self.stall_ctrl.stall_exception(m)

        @def_method(m, self._on_resume)
        def _(ftq_idx, pc, from_exception):
            resume_from_ptr = FTQPtr(gp=self.gen_params)
            m.d.top_comb += resume_from_ptr.eq(Mux(from_exception, commit_ptr, ftq_idx))
            log.info(m, True, "Resuming from pc=0x{:x} ftq_idx={}/{}", pc, resume_from_ptr.parity, resume_from_ptr.ptr)
            pc_queue.redirect(m, ftq_idx=resume_from_ptr, pc=pc)
            prediction_queue.rollback(m, ftq_idx=resume_from_ptr)
            misprediction_reg.clear(m)

        @def_method(m, self.jump_target_req)
        def _(ftq_idx):
            jump_target_mem.read_req(m, addr=ftq_idx.ptr)

        self.jump_target_resp.proxy(m, jump_target_mem.read_resp)

        return m


class MispredictionInfoRegister(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        fields = self.gen_params.get(CommonLayoutFields)

        ftq_layouts = self.gen_params.get(FetchTargetQueueLayouts)

        self.report_misprediction = Method(i=ftq_layouts.report_misprediction)
        self.get = Method(i=make_layout(fields.ftq_addr), o=make_layout(fields.cfi_target, ("valid", 1)))
        self.clear = Method()

    def elaborate(self, platform):
        m = TModule()

        valid = Signal()
        current_misprediction = Signal(self.report_misprediction.layout_in)

        @def_method(m, self.report_misprediction)
        def _(arg):
            current_ftq_idx = FTQPtr(current_misprediction.ftq_addr.ftq_idx, gp=self.gen_params)
            ftq_idx = FTQPtr(arg.ftq_addr.ftq_idx, gp=self.gen_params)
            with m.If(
                ~valid
                | (ftq_idx < current_ftq_idx)
                | (
                    (ftq_idx == current_ftq_idx)
                    & (arg.ftq_addr.fb_instr_idx < current_misprediction.ftq_addr.fb_instr_idx)
                )
            ):
                m.d.sync += valid.eq(1)
                m.d.sync += assign(current_misprediction, arg)

        @def_method(m, self.get)
        def _(ftq_addr):
            return {
                "cfi_target": current_misprediction.cfi_target,
                "valid": valid & (ftq_addr == current_misprediction.ftq_addr),
            }

        @def_method(m, self.clear)
        def _():
            m.d.sync += valid.eq(0)

        return m


class PCQueue(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        fields = self.gen_params.get(CommonLayoutFields)

        self.write = Method(i=make_layout(fields.ftq_idx, fields.pc, fields.global_branch_history, fields.bpu_stage))

        self.bpu_consume = Method(
            o=make_layout(fields.ftq_idx, fields.pc, fields.global_branch_history, fields.bpu_stage)
        )
        self.ifu_consume = Method(o=make_layout(fields.ftq_idx, fields.pc, fields.bpu_stage))

        self.pop = Method()

        self.redirect = Method(i=make_layout(fields.ftq_idx, fields.pc))

        self.ifu_consume_ptr = FTQPtr(gp=self.gen_params)
        self.oldest_ptr = FTQPtr(gp=self.gen_params)

    def elaborate(self, platform):
        m = TModule()

        fields = self.gen_params.get(CommonLayoutFields)
        ifu_queue_layout = make_layout(fields.pc, fields.bpu_stage)

        m.submodules.mem = mem = FTQMemoryWrapper(gen_params=self.gen_params, layout=ifu_queue_layout)
        mem_write_args = Signal.like(mem.write.data_in)

        write_forwarded_args = Signal(self.write.layout_in)

        last_written_slot = FTQPtr(gp=self.gen_params)
        next_write_slot = FTQPtr(gp=self.gen_params)
        m.d.comb += next_write_slot.eq(last_written_slot + 1)

        bpu_request_reg = Signal(make_layout(fields.ftq_idx, fields.pc, fields.bpu_stage, fields.global_branch_history))
        bpu_request_reg_valid = Signal()

        consume_ptr_next = FTQPtr(gp=self.gen_params)
        m.d.comb += consume_ptr_next.eq(self.ifu_consume_ptr)
        m.d.sync += self.ifu_consume_ptr.eq(consume_ptr_next)
        m.d.comb += mem.read_ptr_next.eq(consume_ptr_next)

        # This must be always ready
        @def_method(m, self.write)
        def _(arg) -> None:
            ftq_idx = FTQPtr(arg.ftq_idx, gp=self.gen_params)
            log.debug(m, True, "PC queue write ftq={}/{} pc=0x{:x}", arg.ftq_idx.parity, arg.ftq_idx.ptr, arg.pc)
            log.assertion(m, ftq_idx <= next_write_slot, "FTQ entry must be written in the next free slot or before")
            log.assertion(m, ~bpu_request_reg_valid)

            m.d.sync += last_written_slot.eq(ftq_idx)

            m.d.av_comb += assign(write_forwarded_args, arg)

            with m.If(ftq_idx < self.ifu_consume_ptr):
                m.d.comb += consume_ptr_next.eq(ftq_idx)

            m.d.sync += assign(bpu_request_reg, arg)
            m.d.sync += bpu_request_reg_valid.eq(1)

            m.d.comb += assign(
                mem_write_args, {"ftq_idx": arg.ftq_idx, "data": {"pc": arg.pc, "bpu_stage": arg.bpu_stage}}
            )

        # to avoid combinational loops
        self.write.schedule_before(self.bpu_consume)
        self.write.schedule_before(self.ifu_consume)

        # Only ready when we have space to accept the result of the prediction.
        @def_method(
            m,
            self.bpu_consume,
            ready=(bpu_request_reg_valid & ~FTQPtr.queue_full(next_write_slot, self.oldest_ptr))
            | (self.write.run & ~FTQPtr.queue_full(next_write_slot + 1, self.oldest_ptr)),
        )
        def _():
            m.d.sync += bpu_request_reg_valid.eq(0)
            ret = Signal.like(self.bpu_consume.data_out)
            with m.If(bpu_request_reg_valid):
                m.d.av_comb += assign(ret, bpu_request_reg)
            with m.Else():
                m.d.av_comb += assign(ret, write_forwarded_args)

            log.debug(m, True, "Consuming BPU ftq={}/{} pc=0x{:x}", ret.ftq_idx.parity, ret.ftq_idx.ptr, ret.pc)

            return ret

        consume_queue_nonempty = Signal()
        m.d.comb += consume_queue_nonempty.eq(next_write_slot != self.ifu_consume_ptr)

        called = Signal()

        @def_method(m, self.ifu_consume, ready=consume_queue_nonempty | self.write.run)
        def _():
            ret = Signal.like(self.ifu_consume.data_out)
            with m.If(
                self.write.run & (FTQPtr(write_forwarded_args.ftq_idx, gp=self.gen_params) <= self.ifu_consume_ptr)
            ):
                m.d.av_comb += assign(ret, write_forwarded_args, fields=("ftq_idx", "pc", "bpu_stage"))
            with m.Else():
                m.d.av_comb += assign(
                    ret, {"ftq_idx": self.ifu_consume_ptr, "pc": mem.read_data.pc, "bpu_stage": mem.read_data.bpu_stage}
                )

            log.debug(m, True, "Consuming IFU ftq={}/{} pc=0x{:x}", ret.ftq_idx.parity, ret.ftq_idx.ptr, ret.pc)

            m.d.comb += consume_ptr_next.eq(FTQPtr(ret.ftq_idx, gp=self.gen_params) + 1)

            return ret

        @def_method(m, self.redirect)
        def _(ftq_idx, pc) -> None:
            log.assertion(m, ftq_idx >= self.oldest_ptr, "Cannot rollback before the commit ptr")
            log.info(m, True, "Redirecting FTQ to pc=0x{:x} ftq_idx={}/{}", pc, ftq_idx.parity, ftq_idx.ptr)

            m.d.sync += assign(
                bpu_request_reg, {"ftq_idx": ftq_idx, "pc": pc, "bpu_stage": 0, "global_branch_history": 0}
            )
            m.d.sync += bpu_request_reg_valid.eq(1)

            m.d.comb += assign(mem_write_args, {"ftq_idx": ftq_idx, "data": {"pc": pc, "bpu_stage": 0}})

            m.d.sync += last_written_slot.eq(ftq_idx)
            m.d.comb += consume_ptr_next.eq(ftq_idx)

            m.d.sync += called.eq(1)

        # todo: comment (to avoid conflits on methods)
        with Transaction().body(m, request=self.write.run | self.redirect.run):
            mem.write(m, mem_write_args)

        @def_method(m, self.pop, ready=self.ifu_consume_ptr != self.oldest_ptr)
        def _() -> None:
            m.d.sync += self.oldest_ptr.eq(self.oldest_ptr + 1)

        return m


class PredictionDetailsQueue(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params

        fields = self.gen_params.get(CommonLayoutFields)
        ftq_layouts = self.gen_params.get(FetchTargetQueueLayouts)
        bp_layouts = self.gen_params.get(BranchPredictionLayouts)

        self.write = Method(i=make_layout(fields.ftq_idx, fields.bpu_stage, bp_layouts.block_prediction_field))
        self.try_consume = Method(i=ftq_layouts.consume_prediction_i, o=ftq_layouts.consume_prediction_o)
        self.rollback = Method(i=make_layout(fields.ftq_idx))

    def elaborate(self, platform):
        m = TModule()

        fields = self.gen_params.get(CommonLayoutFields)
        bp_layouts = self.gen_params.get(BranchPredictionLayouts)

        self.mem_layout = make_layout(fields.bpu_stage, bp_layouts.block_prediction_field)

        m.submodules.mem = mem = FTQMemoryWrapper(self.gen_params, layout=self.mem_layout)

        consume_ptr = FTQPtr(gp=self.gen_params)
        m.d.comb += mem.read_ptr_next.eq(consume_ptr)
        m.d.sync += consume_ptr.eq(mem.read_ptr_next)

        write_ptr = FTQPtr(gp=self.gen_params)

        @def_method(m, self.write)
        def _(ftq_idx, bpu_stage, block_prediction) -> None:
            mem.write(m, ftq_idx=ftq_idx, data={"bpu_stage": bpu_stage, "block_prediction": block_prediction})
            m.d.sync += write_ptr.eq(FTQPtr(ftq_idx, gp=self.gen_params) + 1)

        @def_method(m, self.try_consume, ready=consume_ptr != write_ptr)
        def _(ftq_idx, bpu_stage):
            data = mem.read_data

            discard = Signal()
            m.d.av_comb += discard.eq((data.bpu_stage != bpu_stage) | (consume_ptr != ftq_idx))

            with m.If(~discard):
                m.d.comb += mem.read_ptr_next.eq(FTQPtr(ftq_idx, gp=self.gen_params) + 1)

            return {"discard": discard, "block_prediction": data.block_prediction}

        @def_method(m, self.rollback)
        def _(ftq_idx) -> None:
            m.d.comb += mem.read_ptr_next.eq(ftq_idx)
            m.d.sync += write_ptr.eq(FTQPtr(ftq_idx, gp=self.gen_params))

        return m


class StallController(Elaboratable):
    """Frontend of the core."""

    def __init__(self, gen_params: GenParams, on_resume: Method):
        self.gen_params = gen_params

        self.on_resume = on_resume

        layouts = self.gen_params.get(FetchTargetQueueLayouts)
        fields = self.gen_params.get(CommonLayoutFields)

        self.stall_unsafe = Method(i=make_layout(fields.ftq_idx))
        self.stall_exception = Method()

        def resume_combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            from_exception_args = Signal(len(args))
            from_unsafe_args = Signal(len(args))
            m.d.comb += from_exception_args.eq(Cat([arg.from_exception for arg in args]) & runs)
            m.d.comb += from_unsafe_args.eq(Cat([~arg.from_exception for arg in args]) & runs)

            # Make sure that there is at most one caller of each type.
            log.assertion(m, popcount(from_exception_args) <= 1)
            log.assertion(m, popcount(from_unsafe_args) <= 1)

            from_exception = Signal()
            m.d.comb += from_exception.eq(from_exception_args.any())
            pc = Signal.like(args[0].pc)

            for i, v in enumerate(args):
                with m.If((from_exception & from_exception_args[i]) | (~from_exception & from_unsafe_args[i])):
                    m.d.comb += pc.eq(v.pc)

            return {"from_exception": from_exception, "pc": pc}

        self.resume = Method(i=layouts.resume, nonexclusive=True, combiner=resume_combiner)
        self.stall_guard = Method(nonexclusive=True)

    def elaborate(self, platform):
        m = TModule()

        stalled_unsafe = Signal()
        stalled_exception = Signal()

        unsafe_stall_ptr = FTQPtr(gp=self.gen_params)

        @def_method(m, self.stall_guard, ready=~(stalled_unsafe | stalled_exception))
        def _():
            pass

        # todo: remove after nonexclusivity of methods is fixed
        run_resume = Signal()
        resume_args = Signal(self.on_resume.layout_in)

        @def_method(m, self.resume)
        def _(pc, from_exception):
            log.assertion(m, stalled_unsafe | from_exception)

            m.d.sync += stalled_unsafe.eq(0)

            with m.If(from_exception):
                log.assertion(m, stalled_exception)
                m.d.sync += stalled_exception.eq(0)

            m.d.comb += run_resume.eq(1)
            m.d.top_comb += assign(
                resume_args, {"ftq_idx": unsafe_stall_ptr + 1, "pc": pc, "from_exception": from_exception}
            )

            # self.on_resume(m, pc=pc)

        with Transaction().body(m, request=run_resume):
            self.on_resume(m, resume_args)

        @def_method(m, self.stall_unsafe)
        def _(ftq_idx):
            log.assertion(
                m,
                ~stalled_exception,
                "Trying to stall because of an unsafe instruction while being stalled because of an exception",
            )
            log.info(m, True, "Stalling the frontend because of an unsafe instruction")
            m.d.sync += unsafe_stall_ptr.eq(ftq_idx)
            m.d.sync += stalled_unsafe.eq(1)

        # Fetch can be resumed to unstall from 'unsafe' instructions, and stalled because
        # of exception report, both can happen at any time during normal excecution.
        # In case of simultaneous call, fetch will be correctly stalled, becasue separate signal is used
        @def_method(m, self.stall_exception)
        def _():
            log.info(m, ~stalled_exception, "Stalling the frontend because of an exception")
            m.d.sync += stalled_exception.eq(1)

        return m


class FTQMemoryWrapper(Elaboratable):
    """Frontend of the core."""

    def __init__(self, gen_params: GenParams, layout: Layout):
        self.gen_params = gen_params
        self.layout = layout
        self.item_width = self.layout.as_shape().width

        fields = self.gen_params.get(CommonLayoutFields)

        self.write_layout = make_layout(fields.ftq_idx, ("data", self.layout))

        self.read_ptr_next = FTQPtr(gp=self.gen_params)
        self.read_data = Signal(self.layout)

        self.write = Method(i=self.write_layout)

    def elaborate(self, platform):
        m = TModule()

        mem = Memory(width=self.item_width, depth=self.gen_params.ftq_size)
        m.submodules.rdport = rdport = mem.read_port(domain="sync", transparent=True)
        m.submodules.wrport = wrport = mem.write_port()

        m.d.comb += rdport.addr.eq(self.read_ptr_next)
        m.d.comb += self.read_data.eq(rdport.data)

        @def_method(m, self.write)
        def _(ftq_idx, data):
            m.d.comb += wrport.addr.eq(ftq_idx.ptr)
            m.d.comb += wrport.data.eq(data)
            m.d.comb += wrport.en.eq(1)

        return m
