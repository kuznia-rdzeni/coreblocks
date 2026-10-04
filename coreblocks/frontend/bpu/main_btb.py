from amaranth import *
from amaranth.lib import data
from amaranth.lib.enum import Enum

from transactron import *
from transactron.lib import Pipe
from transactron.lib.storage import MemoryBank
from transactron.lib.metrics import *
from transactron.utils import OneHotMux, assign
from transactron.utils.transactron_helpers import make_layout

from coreblocks.params import GenParams, MainBTBConfig
from coreblocks.arch import CfiType
from coreblocks.frontend import FrontendParams
from coreblocks.frontend.bpu.component import CfiPredictor
from coreblocks.cache.random import PseudoRandomGenerator

__all__ = ["MainBTB", "TargetCarry"]


class TargetCarry(Enum, shape=2):
    """Target's high bits relative to the fetch block's."""

    FIT = 0
    OVERFLOW = 1
    """Block's high bits + 1."""
    UNDERFLOW = 2
    """Block's high bits - 1."""


class MainBTB(CfiPredictor):
    """Two-cycle, set-associative BTB with one CFI per way.

    Targets keep only their low bits plus a carry, so a target more than one
    region away from its block just mispredicts.

    Training doesn't reread the SRAM, it decides from the lookup's snapshot. That
    snapshot may be stale, so a CFI can end up in two ways.
    """

    def __init__(self, gen_params: GenParams, config: MainBTBConfig):
        super().__init__(
            gen_params,
            meta_width=config.meta_width(gen_params.fetch_width),
            candidate_count=config.candidate_count(),
        )

        self.config = config
        self.sets = 2**config.sets_log
        self.ways = config.ways
        self.tag_width = config.tag_width
        self.target_width = config.target_width

        xlen = gen_params.isa.xlen
        # Instructions are aligned, so the lowest bits are always zero
        self.target_low_shift = gen_params.min_instr_width_bytes_log
        self.target_high_shift = self.target_low_shift + self.target_width

        block_addr_width = xlen - gen_params.fetch_block_bytes_log
        if config.sets_log > block_addr_width:
            raise ValueError(
                f"Main BTB has {self.sets} sets, but there are only {block_addr_width} fetch block address bits"
            )
        if self.tag_width > block_addr_width - config.sets_log:
            raise ValueError(
                f"Main BTB tag of {self.tag_width} bits is wider than the "
                f"{block_addr_width - config.sets_log} fetch block address bits left above the set index"
            )
        if self.target_high_shift > xlen:
            raise ValueError(f"Main BTB target of {self.target_width} bits does not fit in a {xlen}-bit address")
        if self.target_high_shift < gen_params.fetch_block_bytes_log:
            # All PCs of a block must share their high bits
            raise ValueError(
                f"Main BTB target of {self.target_width} bits is narrower than a fetch block "
                f"of {gen_params.fetch_block_bytes} bytes"
            )

        self.perf_lookups = HwCounter("frontend.bpu.main_btb.lookups", "Number of prediction requests to the main BTB")
        self.perf_hits = TaggedCounter(
            "frontend.bpu.main_btb.hits",
            "Number of CFIs found by main BTB lookups, split by CFI type",
            tags=CfiType,
            ways=self.ways,
        )
        self.perf_block_hits = HwCounter(
            "frontend.bpu.main_btb.block_hits", "Lookups that matched the tag of at least one way"
        )
        self.perf_allocs = HwCounter("frontend.bpu.main_btb.allocs", "Trainings that allocated a new entry")
        self.perf_rewrites = HwCounter("frontend.bpu.main_btb.rewrites", "Trainings that rewrote an existing entry")
        self.perf_out_of_reach = HwCounter(
            "frontend.bpu.main_btb.out_of_reach", "Trainings whose target did not fit in the stored target bits"
        )
        self.perf_duplicates = HwCounter(
            "frontend.bpu.main_btb.duplicates",
            "Trainings that found the CFI stored in more than one way and dropped the extra copies",
        )

    def elaborate(self, platform):
        m = TModule()

        fparams = self.gen_params.get(FrontendParams)
        position_width = self.gen_params.fetch_width_log
        high_width = self.gen_params.isa.xlen - self.target_high_shift

        entry_layout = make_layout(
            ("valid", 1),
            ("tag", self.tag_width),
            ("position", position_width),
            ("cfi_type", CfiType),
            ("target_low", self.target_width),
            ("carry", TargetCarry),
        )
        s1_layout = make_layout(
            ("tag", self.tag_width),
            ("set_idx", range(self.sets)),
            ("position", position_width),
            ("target_high", high_width),
        )
        way_meta_layout = make_layout(("valid", 1), ("raw_hit", 1), ("position", position_width), ("cfi_type", CfiType))

        ways_log = (self.ways - 1).bit_length()
        m.submodules.replacement_random = replacement_random = PseudoRandomGenerator(ways_log)

        m.submodules.s1_pipe = s1_pipe = Pipe(s1_layout)
        m.submodules.s2_pipe = s2_pipe = Pipe(self.component_layouts.cfi_prediction(self.candidate_count))

        m.submodules += [
            self.perf_lookups,
            self.perf_hits,
            self.perf_block_hits,
            self.perf_allocs,
            self.perf_rewrites,
            self.perf_out_of_reach,
            self.perf_duplicates,
        ]

        def set_index(pc: Value) -> Value:
            return fparams.fb_addr(pc)[: self.config.sets_log]

        def tag_of(pc: Value) -> Value:
            return fparams.fb_addr(pc)[self.config.sets_log :][: self.tag_width]

        def target_high(pc: Value) -> Value:
            return pc[self.target_high_shift :]

        def lowest_set(mask: Value) -> Value:
            return mask & -mask

        row_layout = data.ArrayLayout(entry_layout, self.ways)
        m.submodules.table = table = MemoryBank(shape=row_layout, depth=self.sets, granularity=1)

        @def_method(m, self.request_s0)
        def _(pc):
            table.read_req(m, addr=set_index(pc))
            s1_pipe.write(
                m,
                tag=tag_of(pc),
                set_idx=set_index(pc),
                position=fparams.fb_instr_idx(pc),
                target_high=target_high(pc),
            )

        @def_method(m, self.response_s1)
        def _():
            s1 = s1_pipe.read(m)
            row = table.read_resp(m).data
            entries = [row[way] for way in range(self.ways)]

            raw_hit = Signal(self.ways)
            hit = Signal(self.ways)
            m.d.av_comb += [
                raw_hit.eq(Cat(entry.valid & (entry.tag == s1.tag) for entry in entries)),
                hit.eq(raw_hit & Cat(entry.position >= s1.position for entry in entries)),
            ]

            # Hide duplicates, keeping the lowest way
            candidate_valid = Signal(self.ways)
            for way in range(self.ways):
                duplicate = Cat(
                    hit[earlier] & (entries[earlier].position == entries[way].position) for earlier in range(way)
                ).any()
                m.d.av_comb += candidate_valid[way].eq(hit[way] & ~duplicate)

            hints = Signal(self.component_layouts.cfi_hints(self.candidate_count).members["candidates"])
            candidates = Signal(self.component_layouts.cfi_prediction(self.candidate_count).members["candidates"])
            for way, entry in enumerate(entries):
                high = Signal(high_width, name=f"target_high_{way}")
                m.d.av_comb += [
                    high.eq(
                        Mux(
                            entry.carry == TargetCarry.OVERFLOW,
                            s1.target_high + 1,
                            Mux(entry.carry == TargetCarry.UNDERFLOW, s1.target_high - 1, s1.target_high),
                        )
                    ),
                    assign(
                        hints[way],
                        {
                            "valid": candidate_valid[way],
                            "cfi_idx": entry.position,
                            "cfi_type": entry.cfi_type,
                        },
                    ),
                    assign(
                        candidates[way],
                        {
                            "valid": candidate_valid[way],
                            "cfi_idx": entry.position,
                            "cfi_type": entry.cfi_type,
                            "target_valid": candidate_valid[way],
                            "target": Cat(C(0, self.target_low_shift), entry.target_low, high),
                        },
                    ),
                ]

            meta = [Signal(way_meta_layout, name=f"meta_{way}") for way in range(self.ways)]
            for way in range(self.ways):
                m.d.av_comb += assign(
                    meta[way],
                    {
                        "valid": entries[way].valid,
                        "raw_hit": raw_hit[way],
                        "position": entries[way].position,
                        "cfi_type": entries[way].cfi_type,
                    },
                )

            self.perf_lookups.incr(m)
            self.perf_block_hits.incr(m, enable_call=raw_hit.any())
            for way, entry in enumerate(entries):
                self.perf_hits.incr[way](m, tag=entry.cfi_type, enable_call=candidate_valid[way])

            s2_pipe.write(
                m,
                candidates=candidates,
                meta=Cat(meta),
            )

            return {"candidates": hints}

        @def_method(m, self.response_s2)
        def _():
            return s2_pipe.read(m)

        @def_method(m, self.update)
        def _(pc, branch_mask, cfi_target, cfi_idx, cfi_type, taken, mispredict, meta):
            way_meta = [way_meta_layout(meta.word_select(way, way_meta_layout.size)) for way in range(self.ways)]

            set_idx = Signal(range(self.sets))
            m.d.av_comb += set_idx.eq(set_index(pc))

            way_hit = Signal(self.ways)
            hit_oh = Signal(self.ways)
            free = Signal(self.ways)
            free_oh = Signal(self.ways)
            m.d.av_comb += [
                way_hit.eq(Cat(wm.raw_hit & (wm.position == cfi_idx) for wm in way_meta)),
                hit_oh.eq(lowest_set(way_hit)),
                free.eq(Cat(~wm.valid for wm in way_meta)),
                free_oh.eq(lowest_set(free)),
            ]

            victim = replacement_random.value

            def way_of(one_hot: Value) -> Value:
                return OneHotMux.create(m, [(one_hot[way], C(way, range(self.ways))) for way in range(self.ways)])

            hit = Signal()
            write_way = Signal(range(self.ways))
            m.d.av_comb += [
                hit.eq(way_hit.any()),
                write_way.eq(Mux(hit, way_of(hit_oh), Mux(free.any(), way_of(free_oh), victim))),
            ]

            write = Signal()
            m.d.av_comb += write.eq(mispredict & taken & (cfi_type != CfiType.INVALID))

            block_high = Signal(high_width)
            target_high_bits = Signal(high_width)
            carry = Signal(TargetCarry)
            m.d.av_comb += [block_high.eq(target_high(pc)), target_high_bits.eq(target_high(cfi_target))]
            with m.If(target_high_bits == block_high):
                m.d.av_comb += carry.eq(TargetCarry.FIT)
            with m.Elif(target_high_bits == block_high + 1):
                m.d.av_comb += carry.eq(TargetCarry.OVERFLOW)
            with m.Else():
                # Out-of-reach targets land here too and will mispredict.
                m.d.av_comb += carry.eq(TargetCarry.UNDERFLOW)

            entry = Signal(entry_layout)
            m.d.av_comb += assign(
                entry,
                {
                    "valid": 1,
                    "tag": tag_of(pc),
                    "position": cfi_idx,
                    "cfi_type": cfi_type,
                    "target_low": cfi_target[self.target_low_shift : self.target_high_shift],
                    "carry": carry,
                },
            )

            duplicates = Signal(self.ways)
            m.d.av_comb += duplicates.eq(way_hit & ~hit_oh)

            new_row = Signal(row_layout)
            write_mask = Signal(self.ways)
            for way in range(self.ways):
                m.d.av_comb += [
                    assign(new_row[way], entry),
                    write_mask[way].eq((write & (write_way == way)) | duplicates[way]),
                ]
                with m.If(duplicates[way]):
                    m.d.av_comb += new_row[way].valid.eq(0)

            table.write(m, addr=set_idx, data=new_row, mask=write_mask)

            m.d.comb += replacement_random.advance.eq(write & ~hit)

            self.perf_duplicates.incr(m, enable_call=duplicates.any())

            self.perf_allocs.incr(m, enable_call=write & ~hit)
            self.perf_rewrites.incr(m, enable_call=write & hit)
            self.perf_out_of_reach.incr(
                m,
                enable_call=(
                    write
                    & (target_high_bits != block_high)
                    & (target_high_bits != block_high + 1)
                    & (target_high_bits != block_high - 1)
                ),
            )

        return m
