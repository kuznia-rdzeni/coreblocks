from amaranth import *
from transactron import Method, Transaction, def_method, TModule
from coreblocks.interface.layouts import RFLayouts
from coreblocks.params import GenParams
from transactron.lib.metrics import HwExpHistogram, TaggedLatencyMeasurer
from transactron.utils.amaranth_ext.functions import popcount
from transactron.utils.transactron_helpers import make_layout

__all__ = ["RegisterFile"]


class RegisterFile(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RFLayouts)
        self.internal_layout = make_layout(("reg_val", gen_params.isa.xlen), ("valid", 1))
        self.read_layout = layouts.rf_read_out
        self.entries = Array(
            Signal(self.internal_layout, init={"reg_val": 0, "valid": k == 0})
            for k in range(2**gen_params.phys_regs_bits)
        )

        self.read1 = Method(i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.read2 = Method(i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.write = Method(i=layouts.rf_write)
        self.free = Method(i=layouts.rf_free)

        self.perf_rf_valid_time = TaggedLatencyMeasurer(
            "struct.rf.valid_time",
            description="Distribution of time registers are valid in RF",
            slots_number=2**gen_params.phys_regs_bits,
            max_latency=1000,
        )
        self.perf_num_valid = HwExpHistogram(
            "struct.rf.num_valid",
            description="Number of valid registers in RF",
            bucket_count=gen_params.phys_regs_bits + 1,
            sample_width=gen_params.phys_regs_bits + 1,
        )

    def elaborate(self, platform):
        m = TModule()

        m.submodules += [self.perf_rf_valid_time, self.perf_num_valid]

        being_written = Signal(self.gen_params.phys_regs_bits)
        written_value = Signal(self.gen_params.isa.xlen)

        @def_method(m, self.read1)
        def _(reg_id: Value):
            forward = Signal()
            m.d.av_comb += forward.eq((being_written == reg_id) & (reg_id != 0))
            return {
                "reg_val": Mux(forward, written_value, self.entries[reg_id].reg_val),
                "valid": Mux(forward, 1, self.entries[reg_id].valid),
            }

        @def_method(m, self.read2)
        def _(reg_id: Value):
            forward = Signal()
            m.d.av_comb += forward.eq((being_written == reg_id) & (reg_id != 0))
            return {
                "reg_val": Mux(forward, written_value, self.entries[reg_id].reg_val),
                "valid": Mux(forward, 1, self.entries[reg_id].valid),
            }

        @def_method(m, self.write)
        def _(reg_id: Value, reg_val: Value):
            zero_reg = reg_id == 0
            m.d.comb += being_written.eq(reg_id)
            m.d.av_comb += written_value.eq(reg_val)
            with m.If(~(zero_reg)):
                m.d.sync += self.entries[reg_id].reg_val.eq(reg_val)
                m.d.sync += self.entries[reg_id].valid.eq(1)
                self.perf_rf_valid_time.start(m, slot=reg_id)

        @def_method(m, self.free)
        def _(reg_id: Value):
            with m.If(reg_id != 0):
                m.d.sync += self.entries[reg_id].valid.eq(0)
                self.perf_rf_valid_time.stop(m, slot=reg_id)

        if self.perf_num_valid.metrics_enabled():
            num_valid = Signal(self.gen_params.phys_regs_bits + 1)
            m.d.comb += num_valid.eq(
                popcount(Cat(self.entries[reg_id].valid for reg_id in range(2**self.gen_params.phys_regs_bits)))
            )
            with Transaction(name="perf").body(m):
                self.perf_num_valid.add(m, num_valid)

        return m
