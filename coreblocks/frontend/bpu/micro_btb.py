from amaranth import *

from transactron import *
from transactron.lib.metrics import *
from transactron.utils import popcount, logging
from transactron.utils.transactron_helpers import make_layout
from transactron.utils.amaranth_ext.coding import PriorityEncoder

from coreblocks.params import GenParams, MicroBTBConfig
from coreblocks.arch import CfiType
from coreblocks.interface.layouts import BranchPredictionLayouts
from coreblocks.frontend import FrontendParams
from coreblocks.cache.plru import TreePLRU

__all__ = ["MicroBTB"]

log = logging.HardwareLogger("frontend.bpu.btb")


class MicroBTB(Elaboratable):
    """A small, fully-associative, single-cycle branch target buffer (micro-BTB).

    The micro-BTB maps a fetch block address to a predicted next-fetch PC and
    follows an "always-taken on hit" policy: a hit means the block is predicted to
    redirect fetch to the stored target. The lookup is fully associative and
    combinational over a registered request, so a prediction requested in one cycle
    is available in the next cycle.

    Each entry carries a saturating usefulness counter: an entry is valid while
    its counter is non-zero. A correct, taken hit increases the counter; a not-taken
    hit or a hit with a different target decreases it. When the counter reaches zero
    the entry stops matching and becomes a replacement candidate. Replacement prefers
    any such not-useful entry, otherwise it falls back to tree-pseudo-LRU over
    the touched entries.
    """

    def __init__(self, gen_params: GenParams, config: MicroBTBConfig):
        self.gen_params = gen_params

        self.num_entries = 2**config.entries_log
        self.useful_cnt_width = config.useful_cnt_width

        xlen = gen_params.isa.xlen
        # The tag is the full fetch-block address - aliasing is impossible
        # TODO: maybe some aliasing is fine?
        self.tag_width = xlen - gen_params.fetch_block_bytes_log

        self.layouts = gen_params.get(BranchPredictionLayouts)

        self.request = Method(i=self.layouts.predictor_request)
        self.predict = Method(o=self.layouts.predictor_predict)
        self.update = Method(i=self.layouts.update)

        self.perf_lookups = HwCounter("frontend.bpu.ubtb.lookups", "Number of prediction requests to the micro-BTB")
        self.perf_hits = TaggedCounter(
            "frontend.bpu.ubtb.hits", "Number of micro-BTB hits, split by the CFI type of the entry", tags=CfiType
        )
        self.perf_alloc_free = HwCounter("frontend.bpu.ubtb.alloc_free", "Allocations that claimed a not-useful entry")
        self.perf_alloc_evict = HwCounter(
            "frontend.bpu.ubtb.alloc_evict", "Allocations that evicted a still-useful entry"
        )

    def elaborate(self, platform):
        m = TModule()

        fparams = self.gen_params.get(FrontendParams)
        xlen = self.gen_params.isa.xlen
        useful_max = (1 << self.useful_cnt_width) - 1

        entry_layout = make_layout(
            ("tag", self.tag_width),
            ("target", xlen),
            ("cfi_idx", self.gen_params.fetch_width_log),
            ("cfi_type", CfiType),
            ("useful", self.useful_cnt_width),
        )
        entries = [Signal(entry_layout, name=f"entry_{i}") for i in range(self.num_entries)]

        m.submodules.plru = plru = TreePLRU(self.num_entries, touch_ports=2)

        m.submodules += [self.perf_lookups, self.perf_hits, self.perf_alloc_free, self.perf_alloc_evict]

        req_fb = Signal(self.tag_width)
        req_valid = Signal()
        m.d.sync += req_valid.eq(self.request.run)

        def match_vec(fb: Value) -> list[Value]:
            return [(entry.useful != 0) & (entry.tag == fb) for entry in entries]

        # A not-useful entries are preferred over the PLRU victim when allocating
        not_useful = Cat(entry.useful == 0 for entry in entries)
        m.submodules.not_useful_enc = not_useful_enc = PriorityEncoder(self.num_entries)
        m.d.comb += not_useful_enc.i.eq(not_useful)

        @def_method(m, self.request)
        def _(pc):
            m.d.sync += req_fb.eq(fparams.fb_addr(pc))

        @def_method(m, self.predict, ready=req_valid)
        def _():
            hits = Cat(match_vec(req_fb))
            log.assertion(m, popcount(hits) <= 1, "micro-BTB hit vector must be one-hot")

            target = Signal(xlen)
            cfi_idx = Signal(self.gen_params.fetch_width_log)
            cfi_type = Signal(CfiType)
            hit_idx = Signal(range(self.num_entries))
            for i, entry in enumerate(entries):
                with m.If(hits[i]):
                    m.d.av_comb += target.eq(entry.target)
                    m.d.av_comb += cfi_idx.eq(entry.cfi_idx)
                    m.d.av_comb += cfi_type.eq(entry.cfi_type)
                    m.d.av_comb += hit_idx.eq(i)

            # Touch the hit entry so the PLRU keeps frequently-predicted blocks
            with m.If(hits.any()):
                plru.touch[0](m, way=hit_idx)

            self.perf_lookups.incr(m)
            self.perf_hits.incr(m, tag=cfi_type, enable_call=hits.any())

            return {"hit": hits.any(), "cfi_target": target, "cfi_idx": cfi_idx, "cfi_type": cfi_type}

        @def_method(m, self.update)
        def _(pc, cfi_target, cfi_idx, cfi_type, taken, mispredict):
            fb = Signal(self.tag_width)
            m.d.av_comb += fb.eq(fparams.fb_addr(pc))

            matches = match_vec(fb)
            hit = Cat(matches).any()

            hit_idx = Signal(range(self.num_entries))
            for i in range(self.num_entries):
                with m.If(matches[i]):
                    m.d.av_comb += hit_idx.eq(i)

            # Replacement victim: a not-useful entry first, else the PLRU way
            victim_pick = plru.get_victim(m)
            victim = Signal(range(self.num_entries))
            m.d.av_comb += victim.eq(Mux(~not_useful_enc.n, not_useful_enc.o, victim_pick.way))

            # Touch the updated entry: the hit entry, or the victim on a taken miss
            with m.If(hit | taken):
                plru.touch[1](m, way=Mux(hit, hit_idx, victim))

            # An allocation with no not-useful entry available evicts a live entry
            allocating = ~hit & taken
            self.perf_alloc_free.incr(m, enable_call=allocating & ~not_useful_enc.n)
            self.perf_alloc_evict.incr(m, enable_call=allocating & not_useful_enc.n)

            for i, entry in enumerate(entries):
                increased = Mux(entry.useful == useful_max, useful_max, entry.useful + 1)
                decreased = Mux(entry.useful == 0, 0, entry.useful - 1)
                pred_same = (entry.target == cfi_target) & (entry.cfi_idx == cfi_idx) & (entry.cfi_type == cfi_type)

                with m.If(matches[i]):
                    # Reinforce a correct taken hit
                    m.d.sync += entry.useful.eq(Mux(taken & pred_same, increased, decreased))
                with m.Elif(~hit & taken & (victim == i)):
                    m.d.sync += [
                        entry.tag.eq(fb),
                        entry.target.eq(cfi_target),
                        entry.cfi_idx.eq(cfi_idx),
                        entry.cfi_type.eq(cfi_type),
                        entry.useful.eq(useful_max),
                    ]

        return m
