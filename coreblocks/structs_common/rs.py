from typing import Iterable
from amaranth import *
from amaranth.lib.coding import PriorityEncoder
from coreblocks.params.isa import OpType
from coreblocks.transactions import Method, def_method
from coreblocks.params import RSLayouts, GenParams
from coreblocks.transactions.core import RecordDict

__all__ = ["RS"]


class RS(Elaboratable):
    def __init__(self, gen_params: GenParams, ready_for: Iterable[Iterable[OpType]] = ((op for op in OpType),)) -> None:
        self.gen_params = gen_params
        self.layouts = gen_params.get(RSLayouts)
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

        self.ready_for = [list(op_list) for op_list in ready_for]
        self.get_ready_list = [Method(o=self.layouts.get_ready_list_out, nonexclusive=True) for _ in self.ready_for]

        self.data = Array(Record(self.internal_layout) for _ in range(2**self.gen_params.rs_entries_bits))

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.enc_select = PriorityEncoder(width=2**self.gen_params.rs_entries_bits)

        for record in self.data:
            m.d.comb += record.rec_ready.eq(
                ~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool() & record.rec_full.bool()
            )

        select_vector = Cat(~record.rec_reserved for record in self.data)
        select_possible = select_vector.any()

        take_vector = Cat(record.rec_ready & record.rec_full for record in self.data)
        take_possible = take_vector.any()

        ready_lists = []
        for op_list in self.ready_for:
            op_vector = Cat(Cat(record.rs_data.exec_fn.op_type == op for op in op_list).any() for record in self.data)
            ready_lists.append(take_vector & op_vector)

        m.d.comb += m.submodules.enc_select.i.eq(select_vector)

        @def_method(m, self.select, ready=select_possible)
        def _(arg) -> Signal:
            m.d.sync += self.data[m.submodules.enc_select.o].rec_reserved.eq(1)
            return m.submodules.enc_select.o

        @def_method(m, self.insert)
        def _(arg) -> None:
            m.d.sync += self.data[arg.rs_entry_id].rs_data.eq(arg.rs_data)
            m.d.sync += self.data[arg.rs_entry_id].rec_full.eq(1)
            m.d.sync += self.data[arg.rs_entry_id].rec_reserved.eq(1)

        @def_method(m, self.update)
        def _(arg) -> None:
            for record in self.data:
                with m.If(record.rec_full.bool()):
                    with m.If(record.rs_data.rp_s1 == arg.tag):
                        m.d.sync += record.rs_data.rp_s1.eq(0)
                        m.d.sync += record.rs_data.s1_val.eq(arg.value)

                    with m.If(record.rs_data.rp_s2 == arg.tag):
                        m.d.sync += record.rs_data.rp_s2.eq(0)
                        m.d.sync += record.rs_data.s2_val.eq(arg.value)

        @def_method(m, self.take, ready=take_possible)
        def _(arg) -> RecordDict:
            record = self.data[arg.rs_entry_id]
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

        for get_ready_list, ready_list in zip(self.get_ready_list, ready_lists):

            @def_method(m, get_ready_list)
            def _(arg) -> RecordDict:
                return {"ready_list": ready_list}

        return m
