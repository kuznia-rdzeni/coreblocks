from amaranth import *
import amaranth.lib.memory as memory
from transactron import Method, Transaction, def_method, TModule
from coreblocks.interface.layouts import RFLayouts
from coreblocks.params import GenParams
from transactron.lib.metrics import HwExpHistogram, TaggedLatencyMeasurer
from transactron.utils.amaranth_ext.functions import popcount

__all__ = ["RegisterFile"]


class RegisterFile(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RFLayouts)
        self.read_layout = layouts.rf_read_out
        self.entries = memory.Memory(shape=gen_params.isa.xlen, depth=2**gen_params.phys_regs_bits, init=[])
        self.valids = Array(Signal(init=k == 0) for k in range(2**gen_params.phys_regs_bits))

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

        m.submodules += [self.entries, self.perf_rf_valid_time, self.perf_num_valid]

        being_written = Signal(self.gen_params.phys_regs_bits)
        written_value = Signal(self.gen_params.isa.xlen)

        write_port = self.entries.write_port()
        read_port_1 = self.entries.read_port(domain="comb")
        read_port_2 = self.entries.read_port(domain="comb")

        @def_method(m, self.read1)
        def _(reg_id: Value):
            forward = Signal()
            m.d.av_comb += forward.eq((being_written == reg_id) & (reg_id != 0))
            m.d.av_comb += read_port_1.addr.eq(reg_id)
            return {
                "reg_val": Mux(forward, written_value, read_port_1.data),
                "valid": Mux(forward, 1, self.valids[reg_id]),
            }

        @def_method(m, self.read2)
        def _(reg_id: Value):
            forward = Signal()
            m.d.av_comb += forward.eq((being_written == reg_id) & (reg_id != 0))
            m.d.av_comb += read_port_2.addr.eq(reg_id)
            return {
                "reg_val": Mux(forward, written_value, read_port_2.data),
                "valid": Mux(forward, 1, self.valids[reg_id]),
            }

        @def_method(m, self.write)
        def _(reg_id: Value, reg_val: Value):
            zero_reg = reg_id == 0
            m.d.comb += being_written.eq(reg_id)
            m.d.av_comb += written_value.eq(reg_val)
            m.d.av_comb += write_port.addr.eq(reg_id)
            m.d.av_comb += write_port.data.eq(reg_val)
            with m.If(~(zero_reg)):
                m.d.comb += write_port.en.eq(1)
                m.d.sync += self.valids[reg_id].eq(1)
                self.perf_rf_valid_time.start(m, slot=reg_id)

        @def_method(m, self.free)
        def _(reg_id: Value):
            with m.If(reg_id != 0):
                m.d.sync += self.valids[reg_id].eq(0)
                self.perf_rf_valid_time.stop(m, slot=reg_id)

        if self.perf_num_valid.metrics_enabled():
            num_valid = Signal(self.gen_params.phys_regs_bits + 1)
            m.d.comb += num_valid.eq(
                popcount(Cat(self.valids[reg_id] for reg_id in range(2**self.gen_params.phys_regs_bits)))
            )
            with Transaction(name="perf").body(m):
                self.perf_num_valid.add(m, num_valid)

        return m
