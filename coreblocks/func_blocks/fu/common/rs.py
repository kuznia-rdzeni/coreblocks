from abc import abstractmethod
from collections.abc import Iterable
from functools import reduce
from operator import or_
from typing import Optional
from amaranth import *
from amaranth.lib.data import ArrayLayout
from amaranth.utils import ceil_log2
from transactron import Method, Methods, Transaction, def_method, TModule, def_methods
from transactron.lib import logging
from transactron.lib.allocators import PreservedOrderAllocator
from coreblocks.params import GenParams
from coreblocks.arch import OpType
from coreblocks.interface.layouts import RSLayouts
from transactron.lib.metrics import HwExpHistogram, TaggedLatencyMeasurer
from transactron.utils import RecordDict, ValueLike
from transactron.utils import assign
from transactron.utils.assign import AssignType
from transactron.utils.amaranth_ext.functions import popcount
from transactron.utils.transactron_helpers import make_layout

__all__ = ["RSBase", "RS"]


class RSBase(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        rs_entries: int,
        rs_number: int,
        rs_ways: int = 1,
        ready_for: Optional[Iterable[Iterable[OpType]]] = None,
    ) -> None:
        ready_for = ready_for or ((op for op in OpType),)
        self.gen_params = gen_params
        self.rs_entries = rs_entries
        self.rs_ways = rs_ways
        self.layouts = gen_params.get(RSLayouts, rs_entries=self.rs_entries)
        self.internal_layout = make_layout(
            ("rs_data", self.layouts.rs.data_layout),
            ("rec_full", 1),
            ("rec_reserved", 1),
        )

        self.insert = Method(i=self.layouts.rs.insert_in)
        self.select = Method(o=self.layouts.rs.select_out)
        self.update = Methods(rs_ways, i=self.layouts.rs.update_in)
        self.take = Method(i=self.layouts.take_in, o=self.layouts.take_out)

        self.ready_for = [list(op_list) for op_list in ready_for]
        self.get_ready_list = [Method(o=self.layouts.get_ready_list_out) for _ in self.ready_for]

        self.data = Signal(ArrayLayout(self.internal_layout, self.rs_entries))
        self.data_ready = Signal(self.rs_entries)

        self.perf_rs_wait_time = TaggedLatencyMeasurer(
            f"fu.block_{rs_number}.rs.valid_time",
            description=f"Distribution of time instructions wait in RS {rs_number}",
            slots_number=self.rs_entries,
            max_latency=1000,
        )
        self.perf_num_full = HwExpHistogram(
            f"fu.block_{rs_number}.rs.num_full",
            description=f"Number of full entries in RS {rs_number}",
            bucket_count=ceil_log2(self.rs_entries + 1),
            sample_width=ceil_log2(self.rs_entries + 1),
        )
        self.log = logging.HardwareLogger(f"backend.rs.{rs_number}")

    @abstractmethod
    def elaborate(self, platform) -> TModule:
        raise NotImplementedError

    def _elaborate(self, m: TModule, takeable_mask: ValueLike, alloc: Method, free_idx: Method, order: Method):
        m.submodules += [self.perf_rs_wait_time, self.perf_num_full]

        for i, record in enumerate(iter(self.data)):
            m.d.comb += self.data_ready[i].eq(
                ~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool() & record.rec_full
            )

        ready_lists: list[Value] = []
        for op_list in self.ready_for:
            op_vector = Cat(Cat(record.rs_data.exec_fn.op_type == op for op in op_list).any() for record in self.data)
            ready_lists.append(self.data_ready & op_vector)

        @def_method(m, self.select)
        def _() -> RecordDict:
            selected_id = alloc(m).ident
            self.log.debug(m, True, "selected entry {}", selected_id)
            return {"rs_entry_id": selected_id}

        matches_s1 = Signal(ArrayLayout(len(self.update), self.rs_entries))
        matches_s2 = Signal(ArrayLayout(len(self.update), self.rs_entries))

        @def_methods(m, self.update)
        def _(k: int, reg_id: Value, reg_val: Value) -> None:
            for i, record in enumerate(iter(self.data)):
                m.d.comb += matches_s1[i][k].eq(record.rs_data.rp_s1 == reg_id)
                m.d.comb += matches_s2[i][k].eq(record.rs_data.rp_s2 == reg_id)

        # It is assumed that two simultaneous update calls never update the same physical register.
        for i, record in enumerate(iter(self.data)):
            with m.If(matches_s1[i].any()):
                m.d.sync += record.rs_data.rp_s1.eq(0)
                m.d.sync += record.rs_data.s1_val.eq(
                    reduce(or_, (Mux(matches_s1[i][k], self.update[k].data_in.reg_val, 0) for k in range(self.rs_ways)))
                )

            with m.If(matches_s2[i].any()):
                m.d.sync += record.rs_data.rp_s2.eq(0)
                m.d.sync += record.rs_data.s2_val.eq(
                    reduce(or_, (Mux(matches_s2[i][k], self.update[k].data_in.reg_val, 0) for k in range(self.rs_ways)))
                )

        @def_method(m, self.insert)
        def _(rs_entry_id: Value, rs_data: Value) -> None:
            m.d.sync += self.data[rs_entry_id].rs_data.eq(rs_data)
            m.d.sync += self.data[rs_entry_id].rec_full.eq(1)
            self.perf_rs_wait_time.start(m, slot=rs_entry_id)
            self.log.debug(m, True, "inserted entry {}", rs_entry_id)

        with Transaction().body(m):
            self.order = order(m).order  # always ready!

        @def_method(m, self.take)
        def _(rs_entry_id: Value) -> RecordDict:
            actual_rs_entry_id = Signal.like(rs_entry_id)
            m.d.av_comb += actual_rs_entry_id.eq(self.order[rs_entry_id])
            record = self.data[actual_rs_entry_id]
            free_idx(m, idx=rs_entry_id)
            m.d.sync += record.rec_full.eq(0)
            self.perf_rs_wait_time.stop(m, slot=actual_rs_entry_id)
            out = Signal(self.layouts.take_out)
            m.d.av_comb += assign(out, record.rs_data, fields=AssignType.COMMON)
            self.log.debug(m, True, "taken entry {} at idx {}", actual_rs_entry_id, rs_entry_id)
            return out

        for get_ready_list, ready_list in zip(self.get_ready_list, ready_lists):
            reordered_list = Cat(ready_list.bit_select(self.order[i], 1) for i in range(self.rs_entries))

            @def_method(m, get_ready_list, ready=(ready_list & takeable_mask).any(), nonexclusive=True)
            def _() -> RecordDict:
                return {"ready_list": reordered_list}

        if self.perf_num_full.metrics_enabled():
            num_full = Signal(range(self.rs_entries + 1))
            m.d.comb += num_full.eq(popcount(Cat(self.data[entry_id].rec_full for entry_id in range(self.rs_entries))))
            with Transaction(name="perf").body(m):
                self.perf_num_full.add(m, num_full)


class RS(RSBase):
    def elaborate(self, platform):
        m = TModule()

        m.submodules.allocator = allocator = PreservedOrderAllocator(self.rs_entries)

        self._elaborate(m, -1, allocator.alloc, allocator.free_idx, allocator.order)

        return m
