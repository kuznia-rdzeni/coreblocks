from amaranth import *

from transactron.core import *
from transactron.lib import Pipe
from transactron.lib.metrics import HwCounter
from transactron.utils import OneHotMux, logging
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
    write_fetch_target: Required[Method]
    """Pass S1's next fetch PC for an FTQ entry. Called for every request that is not flushed."""
    correct_fetch_target: Required[Method]
    """Replace an FTQ entry's next fetch PC with S2's prediction when it differs from S1's."""
    write_prediction_details: Required[Method]
    update: Provided[Method]
    flush: Provided[Method]
    """Discard every request in the BPU, including one made in the same cycle."""

    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        self.layouts = gen_params.get(BranchPredictionLayouts)
        self.request = Method(i=self.layouts.request)
        self.write_fetch_target = Method(i=self.layouts.fetch_target)
        self.correct_fetch_target = Method(i=self.layouts.fetch_target)
        self.write_prediction_details = Method(i=self.layouts.prediction_details)
        self.update = Method(i=self.layouts.update)
        self.flush = Method()

        self.perf_requests = HwCounter("frontend.bpu.requests", "Prediction requests accepted by the BPU")
        self.perf_s1_redirects = HwCounter(
            "frontend.bpu.s1_redirects", "S1 predictions that redirected fetch to a predicted CFI target"
        )
        self.perf_s2_redirects = HwCounter(
            "frontend.bpu.s2_redirects", "S2 predictions that selected a taken CFI target"
        )
        self.perf_s2_corrections = HwCounter(
            "frontend.bpu.s2_corrections", "S2 predictions that corrected the tentative S1 fetch target"
        )

    def _s2_select(self, m: TModule, stage, candidates, candidate_count: int, taken: Value):
        """Choose S2's prediction: the earliest taken CFI among the CFI predictor's candidates.

        Returns the prediction, the next fetch PC, and whether that PC differs from S1's.
        """
        fetch_layouts = self.gen_params.get(FetchLayouts)
        xlen = self.gen_params.isa.xlen
        ways = range(candidate_count)

        eligible = Signal(candidate_count)
        candidate_taken = Signal(candidate_count)
        matches_s1 = Signal(candidate_count)
        win = Signal(candidate_count)
        branch_mask = C(0, self.gen_params.fetch_width)

        for way in ways:
            candidate = candidates[way]
            m.d.av_comb += [
                eligible[way].eq(candidate.valid & (candidate.cfi_idx >= stage.entry_idx)),
                candidate_taken[way].eq(
                    eligible[way]
                    & candidate.target_valid
                    & ((candidate.cfi_type != CfiType.BRANCH) | taken.bit_select(candidate.cfi_idx, 1))
                ),
                matches_s1[way].eq(candidate.target == stage.s1_next_pc),
            ]
            branch_mask = branch_mask | Mux(
                eligible[way] & (candidate.cfi_type == CfiType.BRANCH), 1 << candidate.cfi_idx, 0
            )

        # The earliest taken slot wins; the lower way breaks ties
        for way in ways:
            beaten_by = [
                candidate_taken[other]
                & (
                    (candidates[other].cfi_idx <= candidates[way].cfi_idx)
                    if other < way
                    else (candidates[other].cfi_idx < candidates[way].cfi_idx)
                )
                for other in ways
                if other != way
            ]
            m.d.av_comb += win[way].eq(candidate_taken[way] & ~Cat(beaten_by).any())

        selected = candidate_taken.any()
        selected_idx = OneHotMux.create(
            m,
            [(win[way], candidates[way].cfi_idx) for way in ways],
            C(0, self.gen_params.fetch_width_log),
        )
        selected_type = OneHotMux.create(
            m,
            [(win[way], Value.cast(candidates[way].cfi_type)) for way in ways],
            C(CfiType.INVALID.value, CfiType.as_shape()),
        )
        selected_target = OneHotMux.create(m, [(win[way], candidates[way].target) for way in ways], C(0, xlen))

        prediction = Signal(fetch_layouts.bpu_prediction)
        next_pc = Signal(xlen)
        correction = Signal()
        m.d.av_comb += [
            prediction.branch_mask.eq(branch_mask),
            prediction.cfi_idx.eq(selected_idx),
            Value.cast(prediction.cfi_type).eq(selected_type),
            prediction.cfi_target.eq(selected_target),
            prediction.cfi_target_valid.eq(selected),
            next_pc.eq(Mux(selected, selected_target, stage.fallthrough)),
            correction.eq(Mux(selected, ~(win & matches_s1).any(), stage.fallthrough != stage.s1_next_pc)),
        ]

        return prediction, next_pc, correction

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [
            self.perf_requests,
            self.perf_s1_redirects,
            self.perf_s2_redirects,
            self.perf_s2_corrections,
        ]

        config = self.gen_params.bpu_config

        m.submodules.fast_predictor = fast = config.fast_predictor.get_module(self.gen_params)

        backing_enabled = config.cfi_predictor is not None
        cfi = config.cfi_predictor.get_module(self.gen_params) if config.cfi_predictor else None
        direction = config.direction_predictor.get_module(self.gen_params) if config.direction_predictor else None

        if backing_enabled:
            assert cfi is not None and direction is not None
            m.submodules.cfi_predictor = cfi
            m.submodules.direction_predictor = direction

        fparams = self.gen_params.get(FrontendParams)
        fields = self.gen_params.get(CommonLayoutFields)
        fetch_layouts = self.gen_params.get(FetchLayouts)

        m.submodules.s1_pipe = s1_pipe = Pipe(
            make_layout(
                fields.pc,
                fields.ftq_ptr,
                ("fallthrough", self.gen_params.isa.xlen),
                ("entry_idx", self.gen_params.fetch_width_log),
                ("live", 1),
            )
        )
        s2_pipe = None
        if backing_enabled:
            s2_layout = [
                fields.pc,
                fields.ftq_ptr,
                ("fallthrough", self.gen_params.isa.xlen),
                ("entry_idx", self.gen_params.fetch_width_log),
                ("s1_next_pc", self.gen_params.isa.xlen),
                ("fast_meta", fast.meta_width),
                ("live", 1),
            ]
            m.submodules.s2_pipe = s2_pipe = Pipe(make_layout(*s2_layout))

        # Flushing a request clears its `live` bit instead of removing it: it still flows
        # through the stages, so the predictors are read out, but its results go nowhere
        s2_flush = Signal()

        @def_method(m, self.request)
        def _(pc, ftq_ptr):
            fast.request_s0(m, pc=pc)
            self.perf_requests.incr(m)

            if backing_enabled:
                assert cfi is not None and direction is not None
                assert s2_pipe is not None
                cfi.request_s0(m, pc=pc)
                direction.request_s0(m, pc=pc)
            s1_pipe.write(
                m,
                pc=pc,
                ftq_ptr=ftq_ptr,
                fallthrough=fparams.pc_from_fb(fparams.fb_addr(pc) + 1, 0),
                entry_idx=fparams.fb_instr_idx(pc),
                live=~self.flush.run,
            )

        # Both stages must run whenever they hold a request, live or not
        with Transaction(name="BPU_S1").always_body(m, log, ready=s1_pipe.read.ready):
            stage = s1_pipe.read(m)
            live = Signal()
            m.d.av_comb += live.eq(stage.live & ~self.flush.run)

            recognized = Signal()
            usable = Signal()
            next_pc = Signal(self.gen_params.isa.xlen)

            fast_prediction = fast.response_s1(m)
            fast_meta = fast_prediction.meta
            m.d.av_comb += [
                recognized.eq(fast_prediction.valid & (fast_prediction.cfi_idx >= stage.entry_idx)),
                usable.eq(recognized & fast_prediction.target_valid),
            ]

            m.d.av_comb += next_pc.eq(Mux(usable, fast_prediction.target, stage.fallthrough))
            self.perf_s1_redirects.incr(m, enable_call=live & usable)
            with m.If(live):
                self.write_fetch_target(m, pc=next_pc, ftq_ptr=stage.ftq_ptr)
            if backing_enabled:
                assert cfi is not None and direction is not None
                assert s2_pipe is not None
                hints = cfi.response_s1(m)
                direction.accept_s1_hints(m, pc=stage.pc, hints=hints)
                s2_pipe.write(
                    m,
                    pc=stage.pc,
                    ftq_ptr=stage.ftq_ptr,
                    fallthrough=stage.fallthrough,
                    entry_idx=stage.entry_idx,
                    s1_next_pc=next_pc,
                    fast_meta=fast_meta,
                    live=live & ~s2_flush,
                )
            else:
                prediction = Signal(fetch_layouts.bpu_prediction)
                m.d.av_comb += [
                    prediction.branch_mask.eq(
                        Mux(recognized & (fast_prediction.cfi_type == CfiType.BRANCH), 1 << fast_prediction.cfi_idx, 0)
                    ),
                    prediction.cfi_idx.eq(fast_prediction.cfi_idx),
                    prediction.cfi_type.eq(Mux(recognized, fast_prediction.cfi_type, CfiType.INVALID)),
                    prediction.cfi_target.eq(fast_prediction.target),
                    prediction.cfi_target_valid.eq(usable),
                ]
                with m.If(live):
                    self.write_prediction_details(
                        m,
                        ftq_ptr=stage.ftq_ptr,
                        pc=stage.pc,
                        prediction=prediction,
                        meta=fast_meta,
                    )

        if backing_enabled:
            assert cfi is not None and direction is not None
            assert s2_pipe is not None
            with Transaction(name="BPU_S2").always_body(m, log, ready=s2_pipe.read.ready):
                stage = s2_pipe.read(m)
                live = Signal()
                m.d.av_comb += live.eq(stage.live & ~self.flush.run)
                cfi_prediction = cfi.response_s2(m)
                direction_prediction = direction.response_s2(m)

                prediction, next_pc, correction = self._s2_select(
                    m, stage, cfi_prediction.candidates, cfi.candidate_count, direction_prediction.taken
                )
                selected = prediction.cfi_target_valid
                self.perf_s2_redirects.incr(m, enable_call=live & selected)
                self.perf_s2_corrections.incr(m, enable_call=live & correction)
                meta = Cat(stage.fast_meta, cfi_prediction.meta, direction_prediction.meta)
                with m.If(live):
                    self.write_prediction_details(
                        m,
                        ftq_ptr=stage.ftq_ptr,
                        pc=stage.pc,
                        prediction=prediction,
                        meta=meta,
                    )

                with m.If(live & correction):
                    self.correct_fetch_target(m, pc=next_pc, ftq_ptr=stage.ftq_ptr)
                    m.d.comb += s2_flush.eq(1)

        @def_method(m, self.update)
        def _(
            pc,
            branch_mask,
            cfi_target,
            cfi_idx,
            cfi_type,
            taken,
            mispredict,
            meta,
        ):
            offset = 0
            predictors = tuple(predictor for predictor in (fast, cfi, direction) if predictor is not None)
            for predictor in predictors:
                predictor.update(
                    m,
                    pc=pc,
                    branch_mask=branch_mask,
                    cfi_target=cfi_target,
                    cfi_idx=cfi_idx,
                    cfi_type=cfi_type,
                    taken=taken,
                    mispredict=mispredict,
                    meta=meta[offset : offset + predictor.meta_width],
                )
                offset += predictor.meta_width

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            pass

        return m
