from amaranth import *
from coreblocks.transactions import Method, def_method
from coreblocks.layouts import RFLayouts
from coreblocks.genparams import GenParams

__all__ = ["RegisterFile"]


class RegisterFile(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RFLayouts)
        self.internal_layout = [("reg_val", gen_params.isa.xlen_log), ("valid", 1)]
        self.read_layout = layouts.rf_read_out
        self.entries = Array(Record(self.internal_layout) for _ in range(2**gen_params.phys_regs_bits))

        self.read1 = Method(i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.read2 = Method(i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.write = Method(i=layouts.rf_write)
        self.free = Method(i=layouts.rf_free)

    def elaborate(self, platform):
        m = Module()

        being_written = Signal(self.gen_params.phys_regs_bits)
        written_value = Signal(self.gen_params.isa.xlen_log)

        @def_method(m, self.read1)
        def _(arg):
            forward = Signal()
            is_zero = Signal()
            forward = being_written == arg.reg_id
            is_zero = arg.reg_id == 0
            return {
                "reg_val": Mux(forward, written_value, Mux(is_zero, 0, self.entries[arg.reg_id].reg_val)),
                "valid": Mux((forward) | (is_zero), 1, self.entries[arg.reg_id].valid),
            }

        @def_method(m, self.read2)
        def _(arg):
            forward = Signal()
            is_zero = Signal()
            forward = being_written == arg.reg_id
            is_zero = arg.reg_id == 0
            return {
                "reg_val": Mux(forward, written_value, Mux(is_zero, 0, self.entries[arg.reg_id].reg_val)),
                "valid": Mux((forward) | (is_zero), 1, self.entries[arg.reg_id].valid),
            }

        @def_method(m, self.write)
        def _(arg):
            m.d.comb += being_written.eq(arg.reg_id)
            m.d.comb += written_value.eq(arg.reg_val)
            m.d.sync += self.entries[arg.reg_id].reg_val.eq(arg.reg_val)
            m.d.sync += self.entries[arg.reg_id].valid.eq(1)

        @def_method(m, self.free)
        def _(arg):
            m.d.sync += self.entries[arg.reg_id].valid.eq(0)

        return m
