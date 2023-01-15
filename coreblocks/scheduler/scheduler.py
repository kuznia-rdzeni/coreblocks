from amaranth import *

from coreblocks.scheduler.rs_selector import RSSelector
from coreblocks.stages.rs_func_block import RSFuncBlock
from coreblocks.transactions import Method, Transaction
from coreblocks.transactions.lib import FIFO
from coreblocks.params import SchedulerLayouts, GenParams
from coreblocks.utils import assign, AssignType

__all__ = ["Scheduler"]


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
            with m.If(instr.regs_l.rl_dst != 0):
                reg_id = self.get_free_reg(m)
                m.d.comb += free_reg.eq(reg_id)

            m.d.comb += assign(data_out, instr)
            m.d.comb += data_out.regs_p.rp_dst.eq(free_reg)
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
            renamed_regs = self.rename(
                m,
                {
                    "rl_s1": instr.regs_l.rl_s1,
                    "rl_s2": instr.regs_l.rl_s2,
                    "rl_dst": instr.regs_l.rl_dst,
                    "rp_dst": instr.regs_p.rp_dst,
                },
            )

            m.d.comb += assign(data_out, instr, fields={"opcode", "illegal", "exec_fn", "imm", "pc"})
            m.d.comb += assign(data_out.regs_l, instr.regs_l, fields=AssignType.COMMON)
            m.d.comb += data_out.regs_p.rp_dst.eq(instr.regs_p.rp_dst)
            m.d.comb += data_out.regs_p.rp_s1.eq(renamed_regs.rp_s1)
            m.d.comb += data_out.regs_p.rp_s2.eq(renamed_regs.rp_s2)
            self.push_instr(m, data_out)

        return m


class ROBAllocation(Elaboratable):
    def __init__(self, *, get_instr: Method, push_instr: Method, rob_put: Method, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rob_allocate_in
        self.output_layout = layouts.rob_allocate_out

        self.get_instr = get_instr
        self.push_instr = push_instr
        self.rob_put = rob_put

    def elaborate(self, platform):
        m = Module()

        data_out = Record(self.output_layout)

        with Transaction().body(m):
            instr = self.get_instr(m)

            rob_id = self.rob_put(
                m,
                {
                    "rl_dst": instr.regs_l.rl_dst,
                    "rp_dst": instr.regs_p.rp_dst,
                },
            )

            m.d.comb += assign(data_out, instr, fields=AssignType.COMMON)
            m.d.comb += data_out.rob_id.eq(rob_id.rob_id)

            self.push_instr(m, data_out)

        return m


class RSInsertion(Elaboratable):
    def __init__(
        self, *, get_instr: Method, rs_insert: list[Method], rf_read1: Method, rf_read2: Method, gen_params: GenParams
    ):
        self.gen_params = gen_params

        self.get_instr = get_instr
        self.rs_insert = rs_insert
        self.rf_read1 = rf_read1
        self.rf_read2 = rf_read2

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            for i in range(len(self.rs_insert)):
                instr = self.get_instr(m)
                source1 = self.rf_read1(m, {"reg_id": instr.regs_p.rp_s1})
                source2 = self.rf_read2(m, {"reg_id": instr.regs_p.rp_s2})

                with m.If(instr.rs_selected == i):
                    self.rs_insert[i](
                        m,
                        {
                            # when operand value is valid the convention is to set operand source to 0
                            "rs_data": {
                                "rp_s1": Mux(source1.valid, 0, instr.regs_p.rp_s1),
                                "rp_s2": Mux(source2.valid, 0, instr.regs_p.rp_s2),
                                "rp_dst": instr.regs_p.rp_dst,
                                "rob_id": instr.rob_id,
                                "exec_fn": instr.exec_fn,
                                "s1_val": Mux(source1.valid, source1.reg_val, 0),
                                "s2_val": Mux(source2.valid, source2.reg_val, 0),
                                "imm": instr.imm,
                                "pc": instr.pc,
                            },
                            "rs_entry_id": instr.rs_entry_id,
                        },
                    )

        return m


class Scheduler(Elaboratable):
    def __init__(
        self,
        *,
        get_instr: Method,
        get_free_reg: Method,
        rat_rename: Method,
        rob_put: Method,
        rf_read1: Method,
        rf_read2: Method,
        reservation_stations: list[RSFuncBlock],
        gen_params: GenParams
    ):
        self.gen_params = gen_params
        self.layouts = self.gen_params.get(SchedulerLayouts)
        self.get_instr = get_instr
        self.get_free_reg = get_free_reg
        self.rat_rename = rat_rename
        self.rob_put = rob_put
        self.rf_read1 = rf_read1
        self.rf_read2 = rf_read2
        self.rs = reservation_stations

    def elaborate(self, platform):
        m = Module()

        m.submodules.alloc_rename_buf = alloc_rename_buf = FIFO(self.layouts.reg_alloc_out, 2)
        m.submodules.reg_alloc = RegAllocation(
            get_instr=self.get_instr,
            push_instr=alloc_rename_buf.write,
            get_free_reg=self.get_free_reg,
            gen_params=self.gen_params,
        )

        m.submodules.rename_out_buf = rename_out_buf = FIFO(self.layouts.renaming_out, 2)
        m.submodules.renaming = Renaming(
            get_instr=alloc_rename_buf.read,
            push_instr=rename_out_buf.write,
            rename=self.rat_rename,
            gen_params=self.gen_params,
        )

        m.submodules.reg_alloc_out_buf = reg_alloc_out_buf = FIFO(self.layouts.rob_allocate_out, 2)
        m.submodules.rob_alloc = ROBAllocation(
            get_instr=rename_out_buf.read,
            push_instr=reg_alloc_out_buf.write,
            rob_put=self.rob_put,
            gen_params=self.gen_params,
        )

        m.submodules.rs_select_out_buf = rs_select_out_buf = FIFO(self.layouts.rs_select_out, 2)
        m.submodules.rs_selector = RSSelector(
            gen_params=self.gen_params,
            get_instr=reg_alloc_out_buf.read,
            rs_select=[(self.rs[i].select, self.rs[i].optypes) for i in range(len(self.rs))],
            push_instr=rs_select_out_buf.write,
        )

        m.submodules.rs_insertion = RSInsertion(
            get_instr=rs_select_out_buf.read,
            rs_insert=[rs.insert for rs in self.rs],
            rf_read1=self.rf_read1,
            rf_read2=self.rf_read2,
            gen_params=self.gen_params,
        )

        return m
