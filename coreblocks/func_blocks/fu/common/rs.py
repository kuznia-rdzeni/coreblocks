from abc import abstractmethod
from collections.abc import Iterable
from typing import Optional
from amaranth import *
from transactron import Method, Transaction, def_method, TModule
from coreblocks.params import GenParams
from coreblocks.arch import OpType
from coreblocks.interface.layouts import RSLayouts
from transactron.lib.metrics import HwExpHistogram, TaggedLatencyMeasurer
from transactron.utils import RecordDict
from transactron.utils import assign
from transactron.utils.assign import AssignType
from transactron.utils.amaranth_ext.coding import PriorityEncoder
from transactron.utils.amaranth_ext.functions import popcount
from transactron.utils.transactron_helpers import make_layout

__all__ = ["RSBase", "RS"]


class RSBase(Elaboratable):
    def __init__(
        self,
        gen_params: GenParams,
        rs_entries: int,
        rs_number: int,
        ready_for: Optional[Iterable[Iterable[OpType]]] = None,
    ) -> None:
        ready_for = ready_for or ((op for op in OpType),)
        self.gen_params = gen_params
        self.rs_entries = rs_entries
        self.rs_entries_bits = (rs_entries - 1).bit_length()
        self.layouts = gen_params.get(RSLayouts, rs_entries_bits=self.rs_entries_bits)
        self.internal_layout = make_layout(
            ("rs_data", self.layouts.rs.data_layout),
            ("rec_full", 1),
            ("rec_reserved", 1),
        )

        self.insert = Method(i=self.layouts.rs.insert_in)
        self.select = Method(o=self.layouts.rs.select_out)
        self.update = Method(i=self.layouts.rs.update_in)
        self.take = Method(i=self.layouts.take_in, o=self.layouts.take_out)

        self.ready_for = [list(op_list) for op_list in ready_for]
        self.get_ready_list = [Method(o=self.layouts.get_ready_list_out) for _ in self.ready_for]

        self.data = Array(Signal(self.internal_layout) for _ in range(self.rs_entries))
        self.data_ready = Signal(self.rs_entries)

        self.perf_rs_wait_time = TaggedLatencyMeasurer(
            f"fu.block_{rs_number}.rs.valid_time",
            description=f"Distribution of time instructions wait in RS {rs_number}",
            slots_number=2**self.rs_entries_bits,
            max_latency=1000,
        )
        self.perf_num_full = HwExpHistogram(
            f"fu.block_{rs_number}.rs.num_full",
            description=f"Number of full entries in RS {rs_number}",
            bucket_count=self.rs_entries_bits + 1,
            sample_width=self.rs_entries_bits + 1,
        )

    @abstractmethod
    def elaborate(self, platform) -> TModule:
        raise NotImplementedError

    def _elaborate(self, m: TModule, selected_id: Value, select_possible: Value, take_vector: Value):
        m.submodules += [self.perf_rs_wait_time, self.perf_num_full]

        for i, record in enumerate(self.data):
            m.d.comb += self.data_ready[i].eq(
                ~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool() & record.rec_full.bool()
            )

        ready_lists: list[Value] = []
        for op_list in self.ready_for:
            op_vector = Cat(Cat(record.rs_data.exec_fn.op_type == op for op in op_list).any() for record in self.data)
            ready_lists.append(take_vector & op_vector)

        @def_method(m, self.select, ready=select_possible)
        def _() -> RecordDict:
            m.d.sync += self.data[selected_id].rec_reserved.eq(1)
            return {"rs_entry_id": selected_id}

        @def_method(m, self.insert)
        def _(rs_entry_id: Value, rs_data: Value) -> None:
            m.d.sync += self.data[rs_entry_id].rs_data.eq(rs_data)
            m.d.sync += self.data[rs_entry_id].rec_full.eq(1)
            m.d.sync += self.data[rs_entry_id].rec_reserved.eq(1)
            self.perf_rs_wait_time.start(m, slot=rs_entry_id)

        @def_method(m, self.update)
        def _(reg_id: Value, reg_val: Value) -> None:
            for record in self.data:
                with m.If(record.rec_full.bool()):
                    with m.If(record.rs_data.rp_s1 == reg_id):
                        m.d.sync += record.rs_data.rp_s1.eq(0)
                        m.d.sync += record.rs_data.s1_val.eq(reg_val)

                    with m.If(record.rs_data.rp_s2 == reg_id):
                        m.d.sync += record.rs_data.rp_s2.eq(0)
                        m.d.sync += record.rs_data.s2_val.eq(reg_val)

        @def_method(m, self.take)
        def _(rs_entry_id: Value) -> RecordDict:
            record = self.data[rs_entry_id]
            m.d.sync += record.rec_reserved.eq(0)
            m.d.sync += record.rec_full.eq(0)
            self.perf_rs_wait_time.stop(m, slot=rs_entry_id)
            out = Signal(self.layouts.take_out)
            m.d.av_comb += assign(out, record.rs_data, fields=AssignType.COMMON)
            return out

        for get_ready_list, ready_list in zip(self.get_ready_list, ready_lists):

            @def_method(m, get_ready_list, ready=ready_list.any(), nonexclusive=True)
            def _() -> RecordDict:
                return {"ready_list": ready_list}

        if self.perf_num_full.metrics_enabled():
            num_full = Signal(self.rs_entries_bits + 1)
            m.d.comb += num_full.eq(popcount(Cat(self.data[entry_id].rec_full for entry_id in range(self.rs_entries))))
            with Transaction(name="perf").body(m):
                self.perf_num_full.add(m, num_full)


class RS(RSBase):
    def elaborate(self, platform):
        m = TModule()

        m.submodules.enc_select = enc_select = PriorityEncoder(width=self.rs_entries)

        select_vector = Cat(~record.rec_reserved for record in self.data)
        select_possible = select_vector.any()

        take_vector = Cat(self.data_ready[i] & record.rec_full for i, record in enumerate(self.data))

        m.d.comb += enc_select.i.eq(select_vector)

        self._elaborate(m, enc_select.o, select_possible, take_vector)

        return m
