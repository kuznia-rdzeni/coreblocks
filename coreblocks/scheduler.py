from amaranth import *
from coreblocks.transactions import Method, Transaction
from coreblocks.layouts import SchedulerLayouts, ROBLayouts
from coreblocks.genparams import GenParams
from coreblocks.utils import AssignType, assign

__all__ = ["RegAllocation", "Renaming", "ROBAllocation"]


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

            m.d.comb += assign(data_out, instr)
            m.d.comb += data_out.rp_dst.eq(free_reg)
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

            m.d.comb += assign(data_out, instr, fields={"rl_dst", "rp_dst", "opcode"})
            m.d.comb += assign(data_out, renamed_regs)
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

            m.d.comb += assign(rob_req, instr, fields={"rl_dst", "rp_dst"})
            rob_id = self.rob_put(m, rob_req)

            m.d.comb += assign(data_out, instr, fields={"rp_s1", "rp_s2", "rp_dst", "opcode"})
            m.d.comb += data_out.rob_id.eq(rob_id.rob_id)

            self.push_instr(m, data_out)

        return m
