from amaranth import *
from amaranth.lib.data import ArrayLayout

from transactron import *
from transactron.utils.transactron_helpers import make_layout

from coreblocks.params import GenParams
from coreblocks.interface.layouts import CommonLayoutFields

__all__ = [
    "BPUComponentLayouts",
    "BPUComponent",
    "FastPredictor",
    "CfiPredictor",
    "DirectionPredictor",
]


class BPUComponentLayouts:
    """Shared predictor layouts."""

    def __init__(self, gen_params: GenParams, *, meta_width: int):
        fields = gen_params.get(CommonLayoutFields)
        self._meta = ("meta", meta_width)

        # S0 request with the fetch PC, which may start within a fetch block.
        self.request = make_layout(fields.pc)

        self.cfi_hint = make_layout(("valid", 1), fields.cfi_idx, fields.cfi_type)
        self.cfi_candidate = make_layout(
            ("valid", 1), fields.cfi_idx, fields.cfi_type, ("target_valid", 1), ("target", gen_params.isa.xlen)
        )

        self.fast_prediction = make_layout(
            ("valid", 1),
            fields.cfi_idx,
            fields.cfi_type,
            ("target_valid", 1),
            ("target", gen_params.isa.xlen),
            self._meta,
        )
        self.direction_prediction = make_layout(("taken", gen_params.fetch_width), self._meta)

        self.update = make_layout(
            fields.pc,
            ("branch_mask", gen_params.fetch_width),
            fields.cfi_target,
            fields.cfi_idx,
            fields.cfi_type,
            ("taken", 1),
            ("mispredict", 1),
            self._meta,
        )

    def cfi_hints(self, candidate_count: int):
        return make_layout(("candidates", ArrayLayout(self.cfi_hint, candidate_count)))

    def cfi_prediction(self, candidate_count: int):
        return make_layout(
            ("candidates", ArrayLayout(self.cfi_candidate, candidate_count)),
            self._meta,
        )


class BPUComponent(Elaboratable):
    """Shared layouts and training interface for BPU components."""

    update: Provided[Method]
    """Train on a resolved CFI using this component's prediction metadata."""

    def __init__(self, gen_params: GenParams, meta_width: int):
        self.gen_params = gen_params
        self.meta_width = meta_width
        self.component_layouts = gen_params.get(BPUComponentLayouts, meta_width=meta_width)

        self.update = Method(i=self.component_layouts.update)

    def elaborate(self, platform) -> TModule:
        raise NotImplementedError()


class FastPredictor(BPUComponent):
    """Predict a CFI and its target in S1 from an S0 request."""

    request_s0: Provided[Method]
    response_s1: Provided[Method]
    flush: Provided[Method]

    def __init__(self, gen_params: GenParams, meta_width: int):
        super().__init__(gen_params, meta_width)
        self.request_s0 = Method(i=self.component_layouts.request)
        self.response_s1 = Method(o=self.component_layouts.fast_prediction)
        self.flush = Method()


class CfiPredictor(BPUComponent):
    """Identify CFIs in S1 and provide their targets in S2 from an S0 request."""

    request_s0: Provided[Method]
    response_s1: Provided[Method]
    response_s2: Provided[Method]
    flush: Provided[Method]

    def __init__(self, gen_params: GenParams, meta_width: int, candidate_count: int):
        super().__init__(gen_params, meta_width)
        self.candidate_count = candidate_count
        self.request_s0 = Method(i=self.component_layouts.request)
        self.response_s1 = Method(o=self.component_layouts.cfi_hints(candidate_count))
        self.response_s2 = Method(o=self.component_layouts.cfi_prediction(candidate_count))
        self.flush = Method()


class DirectionPredictor(BPUComponent):
    """Use an S0 request and S1 CFI hints to predict one taken bit per slot in S2."""

    request_s0: Provided[Method]
    accept_s1_hints: Provided[Method]
    response_s2: Provided[Method]
    flush: Provided[Method]

    def __init__(self, gen_params: GenParams, meta_width: int, candidate_count: int):
        super().__init__(gen_params, meta_width)
        self.request_s0 = Method(i=self.component_layouts.request)
        self.accept_s1_hints = Method(
            i=make_layout(
                ("pc", gen_params.isa.xlen),
                ("hints", self.component_layouts.cfi_hints(candidate_count)),
            )
        )
        self.response_s2 = Method(o=self.component_layouts.direction_prediction)
        self.flush = Method()
