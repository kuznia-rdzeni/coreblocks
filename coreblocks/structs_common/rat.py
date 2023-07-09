from amaranth import *
from transactron import Method, def_method, TModule
from transactron.core import Priority
from coreblocks.params import RATLayouts, GenParams

__all__ = ["FRAT", "RRAT"]


class FRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RATLayouts)
        self.rename_input_layout = layouts.rat_rename_in
        self.rename_output_layout = layouts.rat_rename_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        self.rename = Method(i=self.rename_input_layout, o=self.rename_output_layout)
        self.set_all = Method(i=layouts.rat_regs)
        self.set_all.add_conflict(self.rename, Priority.LEFT)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.set_all)
        def _(arg):
            for i in range(1, self.gen_params.isa.reg_cnt):
                m.d.sync += self.entries[i].eq(arg[str(i)])

        @def_method(m, self.rename)
        def _(rp_dst: Value, rl_dst: Value, rl_s1: Value, rl_s2: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"rp_s1": self.entries[rl_s1], "rp_s2": self.entries[rl_s2]}

        return m


class RRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams):
        self.gen_params = gen_params
        layouts = gen_params.get(RATLayouts)
        self.commit_input_layout = layouts.rat_commit_in
        self.commit_output_layout = layouts.rat_commit_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        self.commit = Method(i=self.commit_input_layout, o=self.commit_output_layout)
        self.get_all = Method(o=layouts.rat_regs)

    def elaborate(self, platform):
        m = TModule()

        commit_bypass = Record(self.commit_input_layout)

        @def_method(m, self.commit)
        def _(rp_dst: Value, rl_dst: Value):
            m.d.comb += commit_bypass.rp_dst.eq(rp_dst)
            m.d.comb += commit_bypass.rl_dst.eq(rl_dst)
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"old_rp_dst": self.entries[rl_dst]}

        @def_method(m, self.get_all)
        def _():
            regs = {}
            for i in range(1, self.gen_params.isa.reg_cnt):
                with m.If(commit_bypass.rl_dst == i):
                    regs[str(i)] = commit_bypass.rp_dst
                with m.Else():
                    regs[str(i)] = self.entries[i]
            return regs

        return m
