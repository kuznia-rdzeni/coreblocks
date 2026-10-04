from amaranth import *
from amaranth.lib import data

from transactron import *
from transactron.lib import Pipe
from transactron.lib.storage import MemoryBank

from coreblocks.arch import CfiType
from coreblocks.frontend import FrontendParams
from coreblocks.frontend.bpu.component import DirectionPredictor
from coreblocks.params import BimodalConfig, GenParams

__all__ = ["Bimodal"]


class Bimodal(DirectionPredictor):
    """Two-cycle, position-indexed bimodal direction predictor.

    Every table row contains one saturating counter per instruction position in a
    fetch block. Counters start weakly not taken.
    """

    def __init__(self, gen_params: GenParams, config: BimodalConfig):
        cfi_config = gen_params.bpu_config.cfi_predictor
        if cfi_config is None:
            raise ValueError("Bimodal requires a CFI predictor to define its S1 hint interface")

        super().__init__(
            gen_params,
            meta_width=config.meta_width(gen_params.fetch_width),
            candidate_count=cfi_config.candidate_count(),
        )

        self.config = config
        self.sets = 2**config.sets_log
        self.counter_width = config.counter_width

    def elaborate(self, platform):
        m = TModule()

        fparams = self.gen_params.get(FrontendParams)
        fetch_width = self.gen_params.fetch_width
        row_layout = data.ArrayLayout(unsigned(self.counter_width), fetch_width)
        counter_max = (1 << self.counter_width) - 1
        initial_counter = (1 << (self.counter_width - 1)) - 1

        m.submodules.table = table = MemoryBank(
            shape=row_layout,
            depth=self.sets,
            granularity=1,
            read_on_resp=True,
            init=[[initial_counter] * fetch_width] * self.sets,
        )

        m.submodules.s2_pipe = s2_pipe = Pipe(self.component_layouts.direction_prediction)

        last_write_valid = Signal()
        last_write_set = Signal(range(self.sets))
        last_write_row = Signal(row_layout)
        last_write_mask = Signal(fetch_width)

        def set_index(pc: Value) -> Value:
            return fparams.fb_addr(pc)[: self.config.sets_log]

        def forward_last_write(row, set_idx: Value) -> None:
            for position in range(fetch_width):
                with m.If(last_write_valid & (last_write_set == set_idx) & last_write_mask[position]):
                    m.d.av_comb += row[position].eq(last_write_row[position])

        @def_method(m, self.request_s0)
        def _(pc):
            table.read_req(m, addr=set_index(pc))

        @def_method(m, self.accept_s1_hints)
        def _(pc, hints):
            row = table.read_resp(m).data

            taken = Cat(row[position][-1] for position in range(fetch_width))
            s2_pipe.write(m, taken=taken, meta=Value.cast(row))

        @def_method(m, self.response_s2)
        def _():
            return s2_pipe.read(m)

        @def_method(m, self.update)
        def _(pc, branch_mask, cfi_target, cfi_idx, cfi_type, taken, mispredict, meta):
            update_set = Signal(range(self.sets))
            base_row = Signal(row_layout)
            updated_row = Signal(row_layout)
            m.d.av_comb += [
                update_set.eq(set_index(pc)),
                base_row.eq(meta),
                updated_row.eq(base_row),
            ]
            forward_last_write(base_row, update_set)

            for position in range(fetch_width):
                old_counter = base_row[position]
                new_counter = Signal(self.counter_width, name=f"updated_counter_{position}")
                position_taken = taken & (cfi_idx == position) & (cfi_type == CfiType.BRANCH)

                with m.If(position_taken):
                    m.d.av_comb += new_counter.eq(Mux(old_counter == counter_max, counter_max, old_counter + 1))
                with m.Else():
                    m.d.av_comb += new_counter.eq(Mux(old_counter == 0, 0, old_counter - 1))

                with m.If(branch_mask[position]):
                    m.d.av_comb += updated_row[position].eq(new_counter)

            table.write(m, addr=update_set, data=updated_row, mask=branch_mask)

            with m.If(branch_mask.any()):
                m.d.sync += [
                    last_write_valid.eq(1),
                    last_write_set.eq(update_set),
                    last_write_row.eq(updated_row),
                    last_write_mask.eq(
                        branch_mask | Mux(last_write_valid & (last_write_set == update_set), last_write_mask, 0)
                    ),
                ]

        return m
