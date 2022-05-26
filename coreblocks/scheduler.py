from amaranth import *
from coreblocks.transactions import Method, Transaction
from coreblocks.transactions.lib import def_method
from coreblocks.layouts import SchedulerLayouts, ROBLayouts
from coreblocks.genparams import GenParams


class RegAllocation(Elaboratable):
    def __init__(
        self,
        *,
        get_instr: Method,
        push_instr: Method,
        get_free_reg: Method,
        gen_params: GenParams
    ):
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
            with m.If(instr.rlog_out != 0):
                reg_id = self.get_free_reg(m)
                m.d.comb += free_reg.eq(reg_id)

            m.d.comb += data_out.rlog_1.eq(instr.rlog_1)
            m.d.comb += data_out.rlog_2.eq(instr.rlog_2)
            m.d.comb += data_out.rlog_out.eq(instr.rlog_out)
            m.d.comb += data_out.rphys_out.eq(free_reg)
            self.push_instr(m, data_out)

        return m


class Renaming(Elaboratable):
    def __init__(
        self, *, get_instr: Method, push_instr: Method, rename: Method, gen_params: GenParams
    ):
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

            m.d.comb += data_out.rlog_out.eq(instr.rlog_out)
            m.d.comb += data_out.rphys_out.eq(instr.rphys_out)
            m.d.comb += data_out.rphys_1.eq(renamed_regs.rphys_1)
            m.d.comb += data_out.rphys_2.eq(renamed_regs.rphys_2)
            self.push_instr(m, data_out)

        return m


class ROBAllocate(Elaboratable):
    def __init__(
        self,
        *,
        get_instr: Method,
        push_instr: Method,
        rob_put: Method,
        gen_params: GenParams
    ):
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

            m.d.comb += rob_req.rl_dst.eq(instr.rlog_out)
            m.d.comb += rob_req.rp_dst.eq(instr.rphys_out)
            rob_id = self.rob_put(m, rob_req)

            m.d.comb += data_out.rphys_1.eq(instr.rphys_1)
            m.d.comb += data_out.rphys_2.eq(instr.rphys_2)
            m.d.comb += data_out.rphys_out.eq(instr.rphys_out)
            m.d.comb += data_out.rob_id.eq(rob_id.rob_id)

            self.push_instr(m, data_out)

        return m


class RAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rat_rename_in
        self.output_layout = layouts.rat_rename_out

        self.entries = Array((Signal(self.gen_params.phys_regs_bits, reset=i) for i in range(32)))

        self.if_rename = Method(i=self.input_layout, o=self.output_layout)

    def elaborate(self, platform):
        m = Module()
        renamed = Record(self.output_layout)

        @def_method(m, self.if_rename)
        def _(arg):
            m.d.comb += renamed.rphys_1.eq(self.entries[arg.rlog_1])
            m.d.comb += renamed.rphys_2.eq(self.entries[arg.rlog_2])
            m.d.sync += self.entries[arg.rlog_out].eq(arg.rphys_out)
            return renamed

        return m
