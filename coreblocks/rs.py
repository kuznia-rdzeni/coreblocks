from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.layouts import RSLayouts
from coreblocks.genparams import GenParams

__all__ = ["RS"]


class RS(Elaboratable):
    def __init__(self, gen_params: GenParams) -> None:
        self.params = gen_params
        layouts = gen_params.get(RSLayouts)
        self.internal_layout = [("rs_data", layouts.data_layout), ("rec_full", 1), ("rec_ready", 1)]

        self.insert = Method(i=layouts.insert_in)
        self.select = Method(o=layouts.select_out)
        self.update = Method(i=layouts.update_in)
        self.push = Method(o=layouts.push_out)

        self.data = Array(Record(self.internal_layout) for _ in range(2**gen_params.rs_entries_bits))

    def elaborate(self, platform) -> Module:
        m = Module()

        select_possible = Cat(~record.rec_full.bool() for record in self.data).any()
        push_possible = Cat(record.rec_ready for record in self.data).any()
        free_entry = Signal(self.params.rs_entries_bits)

        @def_method(m, self.select, ready=select_possible)
        def _(arg):
            # TODO replace with proper priority encoder
            for index, record in enumerate(self.data):
                with m.If(~record.rec_full.bool() & ~free_entry.bool()):
                    m.d.comb += free_entry.eq(index)

            return free_entry

        @def_method(m, self.insert)
        def _(arg):
            m.d.sync += self.data[arg.rs_entry_id].rs_data.eq(arg.rs_data)
            m.d.sync += self.data[arg.rs_entry_id].rec_full.eq(1)
            m.d.sync += self.data[arg.rs_entry_id].rec_ready.eq(~arg.rs_data.rp_s1.bool() & ~arg.rs_data.rp_s2.bool())

        @def_method(m, self.update)
        def _(arg):
            for record in self.data:
                with m.If(record.rs_data.rp_s1 == arg.tag):
                    m.d.sync += record.rs_data.rp_s1.eq(0)
                    m.d.sync += record.rs_data.s1_val.eq(arg.value)

                with m.If(record.rs_data.rp_s2 == arg.tag):
                    m.d.sync += record.rs_data.rp_s2.eq(0)
                    m.d.sync += record.rs_data.s2_val.eq(arg.value)

                m.d.sync += record.rec_ready.eq(~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool())

        @def_method(m, self.push, ready=push_possible)
        def _(arg):
            for record in self.data:
                with m.If(record.rec_ready):
                    pass

        return m
