from amaranth import *

from transactron.core import *
from transactron.lib import Pipe
from transactron.utils import logging
from transactron.utils.transactron_helpers import make_layout

from coreblocks.arch import CfiType
from coreblocks.frontend import FrontendParams
from coreblocks.interface.layouts import (
    BranchPredictionLayouts,
    CommonLayoutFields,
    FetchLayouts,
)
from coreblocks.params import GenParams

log = logging.HardwareLogger("frontend.bpu")


class BranchPredictionUnit(Elaboratable):
    """Branch-prediction pipeline built from the configured predictor composition."""

    request: Provided[Method]
    write_prediction: Required[Method]
    update: Provided[Method]
    flush: Provided[Method]

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.layouts = gen_params.get(BranchPredictionLayouts)

        self.request = Method(i=self.layouts.request)
        self.write_prediction = Method(i=self.layouts.write_prediction)
        self.update = Method(i=self.layouts.update)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        config = self.gen_params.bpu_config

        m.submodules.fast_predictor = fast = config.fast_predictor.get_module(self.gen_params)

        fparams = self.gen_params.get(FrontendParams)
        fields = self.gen_params.get(CommonLayoutFields)
        fetch_layouts = self.gen_params.get(FetchLayouts)

        m.submodules.s1_pipe = s1_pipe = Pipe(
            make_layout(
                fields.pc,
                fields.ftq_ptr,
                ("fallthrough", self.gen_params.isa.xlen),
                ("entry_idx", self.gen_params.fetch_width_log),
            )
        )

        @def_method(m, self.request)
        def _(pc, ftq_ptr):
            fast.request_s0(m, pc=pc)
            s1_pipe.write(
                m,
                pc=pc,
                ftq_ptr=ftq_ptr,
                fallthrough=fparams.pc_from_fb(fparams.fb_addr(pc) + 1, 0),
                entry_idx=fparams.fb_instr_idx(pc),
            )

        with Transaction(name="BPU_S1").body(m):
            stage = s1_pipe.read(m)

            recognized = Signal()
            usable = Signal()
            fast_cfi_idx = Signal(self.gen_params.fetch_width_log)
            fast_cfi_type = Signal(CfiType)
            fast_target = Signal(self.gen_params.isa.xlen)
            next_pc = Signal(self.gen_params.isa.xlen)

            fast_prediction = fast.response_s1(m)
            m.d.av_comb += [
                recognized.eq(fast_prediction.valid & (fast_prediction.cfi_idx >= stage.entry_idx)),
                usable.eq(recognized & fast_prediction.target_valid),
                fast_cfi_idx.eq(fast_prediction.cfi_idx),
                fast_cfi_type.eq(fast_prediction.cfi_type),
                fast_target.eq(fast_prediction.target),
            ]

            m.d.av_comb += next_pc.eq(Mux(usable, fast_target, stage.fallthrough))

            prediction = Signal(fetch_layouts.bpu_prediction)
            m.d.av_comb += [
                prediction.branch_mask.eq(Mux(recognized & (fast_cfi_type == CfiType.BRANCH), 1 << fast_cfi_idx, 0)),
                prediction.cfi_idx.eq(fast_cfi_idx),
                prediction.cfi_type.eq(Mux(recognized, fast_cfi_type, CfiType.INVALID)),
                prediction.cfi_target.eq(fast_target),
                prediction.cfi_target_valid.eq(usable),
            ]
            self.write_prediction(m, pc=next_pc, ftq_ptr=stage.ftq_ptr, prediction=prediction)

        @def_method(m, self.update)
        def _(pc, cfi_target, cfi_idx, cfi_type, taken, mispredict):
            predictors = tuple([fast])
            for predictor in predictors:
                predictor.update(
                    m,
                    pc=pc,
                    branch_mask=C(0, self.gen_params.fetch_width),
                    cfi_target=cfi_target,
                    cfi_idx=cfi_idx,
                    cfi_type=cfi_type,
                    taken=taken,
                    mispredict=mispredict,
                    meta=C(0, predictor.meta_width),
                )

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            s1_pipe.clear(m)
            fast.flush(m)

        return m
