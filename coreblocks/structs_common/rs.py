from typing import Iterable, Optional
from amaranth import *
from amaranth.lib.coding import PriorityEncoder
from transactron import Method, def_method, TModule
from coreblocks.params import RSLayouts, GenParams, OpType
from transactron.core import RecordDict, Priority

__all__ = ["RS"]


class RS(Elaboratable):
    def __init__(
        self, gen_params: GenParams, rs_entries: int, ready_for: Optional[Iterable[Iterable[OpType]]] = None
    ) -> None:
        ready_for = ready_for or ((op for op in OpType),)
        self.gen_params = gen_params
        self.rs_entries = rs_entries
        self.rs_entries_bits = (rs_entries - 1).bit_length()
        self.layouts = gen_params.get(RSLayouts, rs_entries_bits=self.rs_entries_bits)
        self.internal_layout = [
            ("rs_data", self.layouts.data_layout),
            ("rec_full", 1),
            ("rec_ready", 1),
            ("rec_reserved", 1),
        ]

        self.insert = Method(i=self.layouts.insert_in)
        self.select = Method(o=self.layouts.select_out)
        self.update = Method(i=self.layouts.update_in)
        self.take = Method(i=self.layouts.take_in, o=self.layouts.take_out)
        self.clear = Method()

        self.ready_for = [list(op_list) for op_list in ready_for]
        self.get_ready_list = [Method(o=self.layouts.get_ready_list_out, nonexclusive=True) for _ in self.ready_for]

        self.data = Array(Record(self.internal_layout) for _ in range(self.rs_entries))

    def elaborate(self, platform):
        m = TModule()

        m.submodules.enc_select = PriorityEncoder(width=self.rs_entries)

        for record in self.data:
            m.d.comb += record.rec_ready.eq(
                ~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool() & record.rec_full.bool()
            )

        select_vector = Cat(~record.rec_reserved for record in self.data)
        select_possible = select_vector.any()

        take_vector = Cat(record.rec_ready & record.rec_full for record in self.data)
        take_possible = take_vector.any()

        ready_lists: list[Value] = []
        for op_list in self.ready_for:
            op_vector = Cat(Cat(record.rs_data.exec_fn.op_type == op for op in op_list).any() for record in self.data)
            ready_lists.append(take_vector & op_vector)

        m.d.comb += m.submodules.enc_select.i.eq(select_vector)

        @def_method(m, self.select, ready=select_possible)
        def _() -> Signal:
            m.d.sync += self.data[m.submodules.enc_select.o].rec_reserved.eq(1)
            return m.submodules.enc_select.o

        @def_method(m, self.insert)
        def _(rs_entry_id: Value, rs_data: Value) -> None:
            m.d.sync += self.data[rs_entry_id].rs_data.eq(rs_data)
            m.d.sync += self.data[rs_entry_id].rec_full.eq(1)
            m.d.sync += self.data[rs_entry_id].rec_reserved.eq(1)

        @def_method(m, self.update)
        def _(tag: Value, value: Value) -> None:
            for record in self.data:
                with m.If(record.rec_full.bool()):
                    with m.If(record.rs_data.rp_s1 == tag):
                        m.d.sync += record.rs_data.rp_s1.eq(0)
                        m.d.sync += record.rs_data.s1_val.eq(value)

                    with m.If(record.rs_data.rp_s2 == tag):
                        m.d.sync += record.rs_data.rp_s2.eq(0)
                        m.d.sync += record.rs_data.s2_val.eq(value)

        @def_method(m, self.take, ready=take_possible)
        def _(rs_entry_id: Value) -> RecordDict:
            record = self.data[rs_entry_id]
            m.d.sync += record.rec_reserved.eq(0)
            m.d.sync += record.rec_full.eq(0)
            return {
                "s1_val": record.rs_data.s1_val,
                "s2_val": record.rs_data.s2_val,
                "rp_dst": record.rs_data.rp_dst,
                "rob_id": record.rs_data.rob_id,
                "exec_fn": record.rs_data.exec_fn,
                "imm": record.rs_data.imm,
                "pc": record.rs_data.pc,
            }

        self.clear.add_conflict(self.select, priority=Priority.LEFT)
        self.clear.add_conflict(self.insert, priority=Priority.LEFT)
        self.clear.add_conflict(self.update, priority=Priority.LEFT)
        self.clear.add_conflict(self.take, priority=Priority.LEFT)

        @def_method(m, self.clear)
        def _() -> None:
            for entry in self.data:
                m.d.sync += entry.rec_full.eq(0)
                m.d.sync += entry.rec_reserved.eq(0)

        for get_ready_list, ready_list in zip(self.get_ready_list, ready_lists):

            @def_method(m, get_ready_list, ready=ready_list.any())
            def _() -> RecordDict:
                return {"ready_list": ready_list}

        return m
