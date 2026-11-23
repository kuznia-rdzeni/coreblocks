from amaranth import *

from transactron.core import *
from transactron.lib import Pipe
from transactron.lib.metrics import HwCounter
from transactron.utils import OneHotMux, logging
from transactron.utils.transactron_helpers import make_layout

from coreblocks.arch import CfiType
from coreblocks.frontend import FrontendParams
from coreblocks.frontend.bpu.component import CfiPredictor, DirectionPredictor, FastPredictor
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
    """Pass S1's next fetch PC for an FTQ entry. May still be called in a flush cycle."""
    correct_fetch_target: Required[Method]
    """Replace an FTQ entry's next fetch PC with S2's prediction when it differs from S1's."""
    write_prediction_details: Required[Method]
    update: Provided[Method]
    flush: Provided[Method]
    """Discard every request in the BPU, including one made in the same cycle, except that cycle's fetch targets."""

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

    def _s2_select(self, m: TModule, stage, candidates, taken: Value):
        """Choose S2's prediction: the earliest taken CFI among the CFI predictor's candidates.

        Returns the prediction, the next fetch PC, and whether that PC differs from S1's.
        """
        fetch_layouts = self.gen_params.get(FetchLayouts)
        xlen = self.gen_params.isa.xlen
        candidate_count = len(candidates)
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
            [(win[way], candidates[way].cfi_type) for way in ways],
            CfiType.INVALID,
        )
        selected_target = OneHotMux.create(m, [(win[way], candidates[way].target) for way in ways], C(0, xlen))

        prediction = Signal(fetch_layouts.bpu_prediction)
        next_pc = Signal(xlen)
        correction = Signal()
        m.d.av_comb += [
            prediction.branch_mask.eq(branch_mask),
            prediction.cfi_idx.eq(selected_idx),
            prediction.cfi_type.eq(selected_type),
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
        fparams = self.gen_params.get(FrontendParams)
        fields = self.gen_params.get(CommonLayoutFields)
        fetch_layouts = self.gen_params.get(FetchLayouts)
        xlen = self.gen_params.isa.xlen

        s1_layout = [
            fields.pc,
            fields.ftq_ptr,
            ("fallthrough", xlen),
            ("entry_idx", self.gen_params.fetch_width_log),
        ]

        m.submodules.fast_predictor = fast = config.fast_predictor.get_module(self.gen_params)
        m.submodules.s1_pipe = s1_pipe = Pipe(make_layout(*s1_layout))
        components: list[FastPredictor | CfiPredictor | DirectionPredictor] = [fast]
        pipes = [s1_pipe]

        backing = None
        if config.cfi_predictor is not None:
            assert config.direction_predictor is not None
            m.submodules.cfi_predictor = cfi = config.cfi_predictor.get_module(self.gen_params)
            m.submodules.direction_predictor = direction = config.direction_predictor.get_module(self.gen_params)
            m.submodules.s2_pipe = s2_pipe = Pipe(
                make_layout(*s1_layout, ("s1_next_pc", xlen), ("fast_meta", fast.meta_width))
            )
            components += [cfi, direction]
            pipes.append(s2_pipe)
            backing = cfi, direction, s2_pipe

        # Drop every request in flight
        discard = Method(name="discard")

        @def_method(m, discard, nonexclusive=True)
        def _():
            for component in components:
                component.flush(m)
            for pipe in pipes:
                pipe.clear(m)

        live = Signal()
        m.d.comb += live.eq(~self.flush.run)

        @def_method(m, self.request)
        def _(pc, ftq_ptr):
            for component in components:
                component.request_s0(m, pc=pc)
            self.perf_requests.incr(m)
            s1_pipe.write(
                m,
                pc=pc,
                ftq_ptr=ftq_ptr,
                fallthrough=fparams.pc_from_fb(fparams.fb_addr(pc) + 1, 0),
                entry_idx=fparams.fb_instr_idx(pc),
            )

        with Transaction(name="BPU_S1").always_body(m, log, ready=s1_pipe.read.ready):
            stage = s1_pipe.read(m)

            recognized = Signal()
            usable = Signal()
            next_pc = Signal(xlen)

            fast_prediction = fast.response_s1(m)
            m.d.av_comb += [
                recognized.eq(fast_prediction.valid & (fast_prediction.cfi_idx >= stage.entry_idx)),
                usable.eq(recognized & fast_prediction.target_valid),
                next_pc.eq(Mux(usable, fast_prediction.target, stage.fallthrough)),
            ]
            self.perf_s1_redirects.incr(m, enable_call=live & usable)
            self.write_fetch_target(m, pc=next_pc, ftq_ptr=stage.ftq_ptr)

            if backing is not None:
                cfi, direction, s2_pipe = backing
                hints = cfi.response_s1(m)
                direction.accept_s1_hints(m, pc=stage.pc, hints=hints)
                s2_pipe.write(
                    m,
                    pc=stage.pc,
                    ftq_ptr=stage.ftq_ptr,
                    fallthrough=stage.fallthrough,
                    entry_idx=stage.entry_idx,
                    s1_next_pc=next_pc,
                    fast_meta=fast_prediction.meta,
                )
            else:
                # S1 is the last stage
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
                        meta=fast_prediction.meta,
                    )

        if backing is not None:
            cfi, direction, s2_pipe = backing
            with Transaction(name="BPU_S2").always_body(m, log, ready=s2_pipe.read.ready):
                stage = s2_pipe.read(m)
                cfi_prediction = cfi.response_s2(m)
                direction_prediction = direction.response_s2(m)

                prediction, next_pc, correction = self._s2_select(
                    m, stage, cfi_prediction.candidates, direction_prediction.taken
                )
                self.perf_s2_redirects.incr(m, enable_call=live & prediction.cfi_target_valid)
                self.perf_s2_corrections.incr(m, enable_call=live & correction)
                with m.If(live):
                    self.write_prediction_details(
                        m,
                        ftq_ptr=stage.ftq_ptr,
                        pc=stage.pc,
                        prediction=prediction,
                        meta=Cat(stage.fast_meta, cfi_prediction.meta, direction_prediction.meta),
                    )

                with m.If(correction):
                    self.correct_fetch_target(m, pc=next_pc, ftq_ptr=stage.ftq_ptr)
                    discard(m)

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
            for component in components:
                component.update(
                    m,
                    pc=pc,
                    branch_mask=branch_mask,
                    cfi_target=cfi_target,
                    cfi_idx=cfi_idx,
                    cfi_type=cfi_type,
                    taken=taken,
                    mispredict=mispredict,
                    meta=meta[offset : offset + component.meta_width],
                )
                offset += component.meta_width

        @def_method(m, self.flush, nonexclusive=True)
        def _():
            discard(m)

        return m
