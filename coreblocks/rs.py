from amaranth import *
from amaranth.lib.coding import PriorityEncoder
from coreblocks.transactions import Method, def_method
from coreblocks.layouts import RSLayouts
from coreblocks.genparams import GenParams

__all__ = ["RS"]


class RS(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.gen_params = gen_params
        layouts = gen_params.get(RSLayouts)
        self.internal_layout = [
            ("rs_data", layouts.data_layout),
            ("rec_full", 1),
            ("rec_ready", 1),
            ("rec_reserved", 1),
        ]

        self.insert = Method(i=layouts.insert_in)
        self.select = Method(o=layouts.select_out)
        self.update = Method(i=layouts.update_in)
        self.push = Method(o=layouts.push_out)

        self.data = Array(Record(self.internal_layout) for _ in range(2**self.gen_params.rs_entries_bits))

    def elaborate(self, platform) -> Module:
        m = Module()

        m.submodules.enc_select = PriorityEncoder(width=2**self.gen_params.rs_entries_bits)
        m.submodules.enc_push = PriorityEncoder(width=2**self.gen_params.rs_entries_bits)
        select_vector = Cat(~record.rec_reserved for record in self.data)
        select_possible = select_vector.any()
        push_vector = Cat(record.rec_ready for record in self.data)
        push_possible = push_vector.any()

        @def_method(m, self.select, ready=select_possible)
        def _(arg) -> Signal:
            m.d.comb += m.submodules.enc_select.i.eq(select_vector)
            m.d.sync += self.data[m.submodules.enc_select.o].rec_reserved.eq(1)
            return m.submodules.enc_select.o

        @def_method(m, self.insert)
        def _(arg) -> None:
            m.d.sync += self.data[arg.rs_entry_id].rs_data.eq(arg.rs_data)
            m.d.sync += self.data[arg.rs_entry_id].rec_full.eq(1)
            m.d.sync += self.data[arg.rs_entry_id].rec_reserved.eq(1)
            m.d.sync += self.data[arg.rs_entry_id].rec_ready.eq(~arg.rs_data.rp_s1.bool() & ~arg.rs_data.rp_s2.bool())

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

                    m.d.sync += record.rec_ready.eq(~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool())

        @def_method(m, self.push, ready=push_possible)
        def _(arg) -> Record:
            m.d.comb += m.submodules.enc_push.i.eq(push_vector)
            m.d.sync += self.data[m.submodules.enc_push.o].rec_reserved.eq(0)
            m.d.sync += self.data[m.submodules.enc_push.o].rec_full.eq(0)
            m.d.sync += self.data[m.submodules.enc_push.o].rec_ready.eq(0)
            return self.data[m.submodules.enc_push.o].rs_data

        return m
