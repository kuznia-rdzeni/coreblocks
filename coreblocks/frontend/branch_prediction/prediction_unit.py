from amaranth import *
from transactron import *

from coreblocks.params import *
from coreblocks.frontend import FrontendParams
from coreblocks.interface.layouts import BranchPredictionLayouts, FTQPtr
from coreblocks.frontend.branch_prediction.iface import BranchPredictionUnitInterface


__all__ = ["BranchPredictionUnit"]


class BranchPredictionUnit(Elaboratable, BranchPredictionUnitInterface):
    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.layouts = gen_params.get(BranchPredictionLayouts)

        self.request = Method(i=self.layouts.bpu_request)
        self.read_target_pred = Method(o=self.layouts.bpu_read_target_pred)
        self.read_pred_details = Method(o=self.layouts.bpu_read_pred_details)
        self.update = Method(i=self.layouts.bpu_update)
        self.flush = Method(nonexclusive=True)

    def elaborate(self, platform):
        m = TModule()

        fparams = self.gen_params.get(FrontendParams)

        saved_pc = Signal(self.gen_params.isa.xlen)
        saved_ftq_idx = FTQPtr(gp=self.gen_params)
        has_prediction = Signal()

        @def_method(m, self.read_target_pred, ready=has_prediction)
        def _():
            m.d.sync += has_prediction.eq(0)

            next_pc = fparams.pc_from_fb(fparams.fb_addr(saved_pc) + 1, 0)
            return {"ftq_idx": saved_ftq_idx, "pc": next_pc, "bpu_stage": 0, "global_branch_history": 0}

        @def_method(m, self.read_pred_details, ready=has_prediction)
        def _():
            m.d.sync += has_prediction.eq(0)
            prediction = Signal(self.layouts.block_prediction)
            return {"ftq_idx": saved_ftq_idx, "bpu_stage": 0, "bpu_meta": 0, "block_prediction": prediction}

        @def_method(m, self.request)
        def _(pc, ftq_idx, global_branch_history, bpu_stage):
            m.d.sync += saved_pc.eq(pc)
            m.d.sync += saved_ftq_idx.eq(ftq_idx)
            m.d.sync += has_prediction.eq(1)

        @def_method(m, self.update)
        def _(
            fb_addr,
            cfi_target,
            cfi_type,
            cfi_idx,
            cfi_mispredicted,
            cfi_taken,
            branch_mask,
            global_branch_history,
            bpu_meta,
        ):
            pass

        @def_method(m, self.flush)
        def _():
            m.d.sync += has_prediction.eq(0)

        return m
