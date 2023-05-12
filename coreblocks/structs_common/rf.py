from amaranth import *
from coreblocks.transactions import Method, def_method, ModuleX
from coreblocks.params import RFLayouts, GenParams

__all__ = ["RegisterFile"]


class RegisterFile(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RFLayouts)
        self.internal_layout = [("reg_val", gen_params.isa.xlen), ("valid", 1)]
        self.read_layout = layouts.rf_read_out
        self.entries = Array(Record(self.internal_layout) for _ in range(2**gen_params.phys_regs_bits))

        self.read1 = Method(i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.read2 = Method(i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.write = Method(i=layouts.rf_write)
        self.free = Method(i=layouts.rf_free)

    def elaborate(self, platform):
        m = ModuleX()

        being_written = Signal(self.gen_params.phys_regs_bits)
        written_value = Signal(self.gen_params.isa.xlen)

        # Register 0 always valid (this field won't be updated in methods below) - not sure
        # how to set 0th entry valid signal at initialization stage so doing it here instead
        # with a 1-cycle delay. I believe this has to be in sync domain like every other
        # RF entry or else bad things will happen.
        m.d.sync += self.entries[0].valid.eq(1)

        @def_method(m, self.read1)
        def _(reg_id: Value):
            forward = being_written == reg_id
            return {
                "reg_val": Mux(forward, written_value, self.entries[reg_id].reg_val),
                "valid": Mux(forward, 1, self.entries[reg_id].valid),
            }

        @def_method(m, self.read2)
        def _(reg_id: Value):
            forward = being_written == reg_id
            return {
                "reg_val": Mux(forward, written_value, self.entries[reg_id].reg_val),
                "valid": Mux(forward, 1, self.entries[reg_id].valid),
            }

        @def_method(m, self.write)
        def _(reg_id: Value, reg_val: Value):
            zero_reg = reg_id == 0
            m.d.comb += being_written.eq(reg_id)
            m.d.comb += written_value.eq(Mux(zero_reg, 0, reg_val))
            with m.If(~(zero_reg)):
                m.d.sync += self.entries[reg_id].reg_val.eq(reg_val)
                m.d.sync += self.entries[reg_id].valid.eq(1)

        @def_method(m, self.free)
        def _(reg_id: Value):
            with m.If(reg_id != 0):
                m.d.sync += self.entries[reg_id].valid.eq(0)

        return m
