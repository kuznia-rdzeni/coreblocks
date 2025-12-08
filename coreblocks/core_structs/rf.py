from amaranth import *
from amaranth.lib.data import ArrayLayout
from amaranth.lib import memory
from transactron import Methods, Transaction, def_methods, TModule
from transactron.utils.amaranth_ext.elaboratables import OneHotMux
from coreblocks.interface.layouts import RFLayouts
from coreblocks.params import GenParams
from transactron.lib import logging
from transactron.lib.metrics import HwExpHistogram, TaggedLatencyMeasurer
from transactron.lib.storage import MemoryBank
from transactron.utils.amaranth_ext.functions import popcount

__all__ = ["RegisterFile"]

log = logging.HardwareLogger("core_structs.rf")


class RegisterFile(Elaboratable):
    def __init__(self, *, gen_params: GenParams, read_ports: int, write_ports: int, free_ports: int):
        self.gen_params = gen_params

        layouts = gen_params.get(RFLayouts)
        self.read_layout = layouts.rf_read_out
        self.entries = MemoryBank(
            memory_type=gen_params.multiport_memory_type if write_ports > 1 else memory.Memory,
            shape=gen_params.isa.xlen,
            depth=2**gen_params.phys_regs_bits,
            read_ports=read_ports,
            write_ports=write_ports,
            transparent=True,
        )
        self.valids = Array(Signal(init=k == 0) for k in range(2**gen_params.phys_regs_bits))

        self.read_req = Methods(read_ports, i=layouts.rf_read_in)
        self.read_resp = Methods(read_ports, i=layouts.rf_read_in, o=layouts.rf_read_out)
        self.write = Methods(write_ports, i=layouts.rf_write)
        self.free = Methods(free_ports, i=layouts.rf_free)

        self.perf_rf_valid_time = TaggedLatencyMeasurer(
            "struct.rf.valid_time",
            description="Distribution of time registers are valid in RF",
            slots_number=2**gen_params.phys_regs_bits,
            max_latency=1000,
            ways=max(write_ports, free_ports),
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

        being_written = Signal(ArrayLayout(self.gen_params.phys_regs_bits, len(self.write)))
        written_value = Signal(ArrayLayout(self.gen_params.isa.xlen, len(self.write)))

        @def_methods(m, self.read_req)
        def _(k: int, reg_id: Value):
            self.entries.read_req[k](m, addr=reg_id)

        @def_methods(m, self.read_resp)
        def _(k: int, reg_id: Value):
            forward = Signal()
            reg_written = Signal(len(self.write))
            m.d.av_comb += reg_written.eq(
                Cat((being_written[i] == reg_id) & (reg_id != 0) for i in range(len(self.write)))
            )
            m.d.av_comb += forward.eq(reg_written.any())
            reg_val = OneHotMux.create(
                m,
                [(reg_written[i], written_value[i]) for i in range(len(self.write))],
                self.entries.read_resp[k](m).data,
            )
            return {
                "reg_val": reg_val,
                "valid": forward | self.valids[reg_id],
            }

        @def_methods(m, self.write)
        def _(k: int, reg_id: Value, reg_val: Value):
            m.d.comb += being_written[k].eq(reg_id)
            m.d.av_comb += written_value[k].eq(reg_val)
            with m.If(reg_id != 0):
                log.assertion(m, ~self.valids[reg_id], "Valid register {} written", reg_id)
                self.entries.write[k](m, addr=reg_id, data=reg_val)
                m.d.sync += self.valids[reg_id].eq(1)
                self.perf_rf_valid_time.start[k](m, slot=reg_id)

        @def_methods(m, self.free)
        def _(k: int, reg_id: Value):
            with m.If(reg_id != 0):
                log.assertion(m, self.valids[reg_id], "Invalid register {} freed", reg_id)
                m.d.sync += self.valids[reg_id].eq(0)
                self.perf_rf_valid_time.stop[k](m, slot=reg_id)

        # It is assumed that two simultaneous write calls never write the same physical register.
        for k1, m1 in enumerate(self.write):
            for k2, m2 in enumerate(self.write[k1 + 1 :]):
                log.error(
                    m,
                    m1.run & m2.run & (m1.data_in.reg_id == m2.data_in.reg_id) & (m1.data_in.reg_id != 0),
                    "Write methods {} and {} both called with reg_id {}",
                    k1,
                    k2,
                    m1.data_in.reg_id,
                )

        # It is assumed that two simultaneous free calls never free the same physical register.
        for k1, m1 in enumerate(self.free):
            for k2, m2 in enumerate(self.free[k1 + 1 :]):
                log.error(
                    m,
                    m1.run & m2.run & (m1.data_in.reg_id == m2.data_in.reg_id) & (m1.data_in.reg_id != 0),
                    "Free methods {} and {} both called with reg_id {}",
                    k1,
                    k2,
                    m1.data_in.reg_id,
                )

        if self.perf_num_valid.metrics_enabled():
            num_valid = Signal(self.gen_params.phys_regs_bits + 1)
            m.d.comb += num_valid.eq(
                popcount(Cat(self.valids[reg_id] for reg_id in range(2**self.gen_params.phys_regs_bits)))
            )
            with Transaction(name="perf").body(m):
                self.perf_num_valid.add(m, num_valid)

        return m
