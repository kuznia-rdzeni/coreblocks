from amaranth import *
from amaranth.lib.coding import PriorityEncoder
from coreblocks.transactions import Method, def_method
from coreblocks.params import RSLayouts, GenParams

__all__ = ["RS"]


class RS(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
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
        self.get_ready_list = Method(o=self.layouts.get_ready_list_out)

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
        take_data_out = Record(self.layouts.take_out)

        ready_list = Record(self.layouts.get_ready_list_out)

        m.d.comb += ready_list.ready_list.eq(take_vector)
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
        def _(arg) -> Record:
            record = self.data[arg.rs_entry_id]
            m.d.sync += record.rec_reserved.eq(0)
            m.d.sync += record.rec_full.eq(0)
            m.d.comb += take_data_out.s1_val.eq(record.rs_data.s1_val)
            m.d.comb += take_data_out.s2_val.eq(record.rs_data.s2_val)
            m.d.comb += take_data_out.rp_dst.eq(record.rs_data.rp_dst)
            m.d.comb += take_data_out.rob_id.eq(record.rs_data.rob_id)
            m.d.comb += take_data_out.exec_fn.eq(record.rs_data.exec_fn)
            m.d.comb += take_data_out.imm.eq(record.rs_data.imm)
            m.d.comb += take_data_out.pc.eq(record.rs_data.pc)
            return take_data_out

        @def_method(m, self.get_ready_list)
        def _(arg) -> Record:
            return ready_list

        return m
