from amaranth import *
from coreblocks.transactions import Method, Transaction
from coreblocks.layouts import SchedulerLayouts
from coreblocks.genparams import GenParams

class RegAllocation(Elaboratable):
    def __init__(self, *, get_instr : Method, push_instr : Method, get_free_reg : Method, layouts : SchedulerLayouts, gen_params : GenParams):
        self.get_free_reg = get_free_reg
        self.gen_params = gen_params
        self.input_layout = layouts.reg_alloc_in
        self.output_layout = layouts.reg_alloc_out
        self.get_instr = get_instr
        self.push_instr = push_instr

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
    def __init__(self, *, get_instr : Method, push_instr : Method, rename : Method, layouts : SchedulerLayouts, gen_params : GenParams):
        self.input_layout = layouts.renaming_in
        self.output_layout = layouts.renaming_out
        self.gen_params = gen_params
        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rename = rename

    def elaborate(self, platform):
        m = Module()

        data_in = Record(self.input_layout)
        data_out = Record(self.output_layout)
        rphys_1 = Signal(self.gen_params.phys_regs_bits)
        rphys_2 = Signal(self.gen_params.phys_regs_bits)

        with Transaction().body(m):
            instr = self.get_instr(m)
            renamed_regs = self.rename(m, instr)

            m.d.comb += data_out.rlog_out.eq(instr.rlog_out)
            m.d.comb += data_out.rphys_out.eq(instr.rphys_out)
            m.d.comb += data_out.rphys_1.eq(renamed_regs.rphys_1)
            m.d.comb += data_out.rphys_2.eq(renamed_regs.rphys_2)
            self.push_instr(m, data_out)

        return m

class RAT(Elaboratable):
    def __init__(self, *, layouts : SchedulerLayouts, gen_params : GenParams):
        self.input_layout = layouts.rat_rename_in
        self.output_layout = layouts.rat_rename_out
        
        self.gen_params = gen_params
        self.entries = Array((Signal(self.gen_params.phys_regs_bits, reset=i) for i in range(32)))

        self.if_rename = Method(i=self.input_layout, o=self.output_layout)

    def elaborate(self, platform):
        m = Module()
        renamed = Record(self.output_layout)

        with self.if_rename.body(m, out=renamed) as arg:
            m.d.comb += renamed.rphys_1.eq(self.entries[arg.rlog_1])
            m.d.comb += renamed.rphys_2.eq(self.entries[arg.rlog_2])
            m.d.sync += self.entries[arg.rlog_out].eq(arg.rphys_out)
        return m