from amaranth import *
from coreblocks.transactions import Method, def_method, TModule, loop_def_method
from coreblocks.params import RATLayouts, GenParams

__all__ = ["FRAT", "RRAT"]


class FRAT(Elaboratable):
    def __init__(self, *, gen_params: GenParams, superscalarity : int = 1):
        self.gen_params = gen_params
        self.superscalarity = superscalarity
        layouts = gen_params.get(RATLayouts)
        self.rename_input_layout = layouts.rat_rename_in
        self.rename_output_layout = layouts.rat_rename_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        if self.superscalarity<1:
            raise ValueError(f"FRAT should have minimum one method, so superscalarity>=1, got: {self.superscalarity}")
        self.rename_list = [Method(i=self.rename_input_layout, o=self.rename_output_layout) for _ in range(self.superscalarity)]
        # for backward compatibility
        self.rename = self.rename_list[0]

    def elaborate(self, platform):
        m = TModule()

        @loop_def_method(m, self.rename_list)
        def _(_, rp_dst: Value, rl_dst: Value, rl_s1: Value, rl_s2: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"rp_s1": self.entries[rl_s1], "rp_s2": self.entries[rl_s2]}

        return m


class RRAT(Elaboratable):
    """
    Assumption about uniques
    """
    def __init__(self, *, gen_params: GenParams, superscalarity : int = 1):
        self.gen_params = gen_params
        self.superscalarity = superscalarity
        layouts = gen_params.get(RATLayouts)
        self.commit_input_layout = layouts.rat_commit_in
        self.commit_output_layout = layouts.rat_commit_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits) for _ in range(self.gen_params.isa.reg_cnt))

        if self.superscalarity<1:
            raise ValueError(f"FRAT should have minimum one method, so superscalarity>=1, got: {self.superscalarity}")
        self.commit_list = [Method(i=self.commit_input_layout, o=self.commit_output_layout) for _ in range(self.superscalarity)]
        # for backward compatibility
        self.commit = self.commit_list[0]

    def elaborate(self, platform):
        m = TModule()

        @loop_def_method(m, self.commit_list)
        def _(_, rp_dst: Value, rl_dst: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"old_rp_dst": self.entries[rl_dst]}

        return m
