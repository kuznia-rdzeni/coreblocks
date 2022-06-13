from amaranth import *
from coreblocks.transactions import Method, Transaction, def_method
from coreblocks.layouts import SchedulerLayouts, ROBLayouts, RFLayouts
from coreblocks.genparams import GenParams

__all__ = ["RegAllocation", "Renaming", "ROBAllocation", "RSSelection", "RSInsertion", "RegisterFile"]


class RegAllocation(Elaboratable):
    def __init__(self, *, get_instr: Method, push_instr: Method, get_free_reg: Method, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.reg_alloc_in
        self.output_layout = layouts.reg_alloc_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.get_free_reg = get_free_reg

    def elaborate(self, platform):
        m = Module()

        free_reg = Signal(self.gen_params.phys_regs_bits)
        data_out = Record(self.output_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)
            with m.If(instr.rl_dst != 0):
                reg_id = self.get_free_reg(m)
                m.d.comb += free_reg.eq(reg_id)

            m.d.comb += data_out.rl_s1.eq(instr.rl_s1)
            m.d.comb += data_out.rl_s2.eq(instr.rl_s2)
            m.d.comb += data_out.rl_dst.eq(instr.rl_dst)
            m.d.comb += data_out.rp_dst.eq(free_reg)
            m.d.comb += data_out.opcode.eq(instr.opcode)
            self.push_instr(m, data_out)

        return m


class Renaming(Elaboratable):
    def __init__(self, *, get_instr: Method, push_instr: Method, rename: Method, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.renaming_in
        self.output_layout = layouts.renaming_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rename = rename

    def elaborate(self, platform):
        m = Module()

        data_out = Record(self.output_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)
            renamed_regs = self.rename(m, instr)

            m.d.comb += data_out.rl_dst.eq(instr.rl_dst)
            m.d.comb += data_out.rp_dst.eq(instr.rp_dst)
            m.d.comb += data_out.rp_s1.eq(renamed_regs.rp_s1)
            m.d.comb += data_out.rp_s2.eq(renamed_regs.rp_s2)
            m.d.comb += data_out.opcode.eq(instr.opcode)
            self.push_instr(m, data_out)

        return m


class ROBAllocation(Elaboratable):
    def __init__(self, *, get_instr: Method, push_instr: Method, rob_put: Method, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rob_allocate_in
        self.output_layout = layouts.rob_allocate_out
        self.rob_req_layout = gen_params.get(ROBLayouts).data_layout

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rob_put = rob_put

    def elaborate(self, platform):
        m = Module()

        data_out = Record(self.output_layout)
        rob_req = Record(self.rob_req_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)

            m.d.comb += rob_req.rl_dst.eq(instr.rl_dst)
            m.d.comb += rob_req.rp_dst.eq(instr.rp_dst)
            rob_id = self.rob_put(m, rob_req)

            m.d.comb += data_out.rp_s1.eq(instr.rp_s1)
            m.d.comb += data_out.rp_s2.eq(instr.rp_s2)
            m.d.comb += data_out.rp_dst.eq(instr.rp_dst)
            m.d.comb += data_out.rob_id.eq(rob_id.rob_id)
            m.d.comb += data_out.opcode.eq(instr.opcode)

            self.push_instr(m, data_out)

        return m


class RSSelection(Elaboratable):
    def __init__(self, *, get_instr: Method, push_instr: Method, rs_alloc: Method, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rs_select_in
        self.output_layout = layouts.rs_select_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rs_alloc = rs_alloc

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            instr = self.get_instr(m)
            allocated_field = self.rs_alloc(m)
            self.push_instr(
                m,
                {
                    "rp_s1": instr.rp_s1,
                    "rp_s2": instr.rp_s2,
                    "rp_dst": instr.rp_dst,
                    "rob_id": instr.rob_id,
                    "opcode": instr.opcode,
                    "rs_entry_id": allocated_field.entry_id,
                },
            )

        return m


class RSInsertion(Elaboratable):
    def __init__(
        self, *, get_instr: Method, rs_insert: Method, rf_read1: Method, rf_read2: Method, gen_params: GenParams
    ):
        self.gen_params = gen_params

        self.get_instr = get_instr
        self.rs_insert = rs_insert
        self.rf_read1 = rf_read1
        self.rf_read2 = rf_read2

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            instr = self.get_instr(m)
            source1 = self.rf_read1(m, {"reg_id": instr.rp_s1})
            source2 = self.rf_read2(m, {"reg_id": instr.rp_s2})

            self.rs_insert(
                m,
                {
                    "rp_s1": instr.rp_s1,
                    "rp_s2": instr.rp_s2,
                    "rp_dst": instr.rp_dst,
                    "rob_id": instr.rob_id,
                    "opcode": instr.opcode,
                    "rs_entry_id": instr.rs_entry_id,
                    "s1_val": Mux(source1.valid, source1.reg_val, 0),
                    "s2_val": Mux(source2.valid, source2.reg_val, 0),
                },
            )

        return m


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
            forward = being_written == arg.reg_id
            return {
                "reg_val": Mux(forward, written_value, self.entries[arg.reg_id].reg_val),
                "valid": Mux(forward, 1, self.entries[arg.reg_id].valid),
            }

        @def_method(m, self.read2)
        def _(arg):
            forward = Signal()
            forward = being_written == arg.reg_id
            return {
                "reg_val": Mux(forward, written_value, self.entries[arg.reg_id].reg_val),
                "valid": Mux(forward, 1, self.entries[arg.reg_id].valid),
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
