from amaranth import *

from transactron import *
from transactron.utils import popcount, logging
from transactron.utils.transactron_helpers import make_layout
from transactron.utils.amaranth_ext.coding import PriorityEncoder

from coreblocks.params import GenParams
from coreblocks.arch import CfiType
from coreblocks.frontend import FrontendParams
from coreblocks.cache.plru import TreePLRU

__all__ = ["MicroBTB"]

log = logging.HardwareLogger("frontend.bpu.btb")


class MicroBTB(Elaboratable):
    """A small, fully-associative, single-cycle branch target buffer (micro-BTB)."""

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

        config = gen_params.bpu_config
        self.num_entries = 2**config.ubtb_entries_log
        self.useful_cnt_width = config.ubtb_useful_cnt_width

        xlen = gen_params.isa.xlen
        # The tag is the full fetch-block address - aliasing is impossible
        # TODO: maybe some aliasing is fine?
        self.tag_width = xlen - gen_params.fetch_block_bytes_log

        cfi_idx_width = gen_params.fetch_width_log

        self.request_layout = make_layout(("pc", xlen))
        self.predict_layout = make_layout(
            ("hit", 1), ("target", xlen), ("cfi_idx", cfi_idx_width), ("cfi_type", CfiType)
        )
        self.update_layout = make_layout(
            ("pc", xlen), ("target", xlen), ("cfi_idx", cfi_idx_width), ("cfi_type", CfiType), ("taken", 1)
        )

        self.request = Method(i=self.request_layout)
        self.predict = Method(o=self.predict_layout)
        self.update = Method(i=self.update_layout)

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

            return {"hit": hits.any(), "target": target, "cfi_idx": cfi_idx, "cfi_type": cfi_type}

        @def_method(m, self.update)
        def _(pc, target, cfi_idx, cfi_type, taken):
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

            for i, entry in enumerate(entries):
                increased = Mux(entry.useful == useful_max, useful_max, entry.useful + 1)
                decreased = Mux(entry.useful == 0, 0, entry.useful - 1)
                pred_same = (entry.target == target) & (entry.cfi_idx == cfi_idx) & (entry.cfi_type == cfi_type)

                with m.If(matches[i]):
                    # Reinforce a correct taken hit
                    m.d.sync += entry.useful.eq(Mux(taken & pred_same, increased, decreased))
                with m.Elif(~hit & taken & (victim == i)):
                    m.d.sync += [
                        entry.tag.eq(fb),
                        entry.target.eq(target),
                        entry.cfi_idx.eq(cfi_idx),
                        entry.cfi_type.eq(cfi_type),
                        entry.useful.eq(useful_max),
                    ]

        return m
