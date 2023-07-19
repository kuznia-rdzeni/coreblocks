from amaranth import *
from coreblocks.transactions import Method, TModule, loop_def_method
from coreblocks.params import RATLayouts, GenParams

__all__ = ["FRAT", "RRAT"]


class FRAT(Elaboratable):
    """Frontend Register Alias Table

    Module to store the translation from logical register
    id's to physical register id's. It can handle up to
    `superscalarity` requests simultaneously.

    Attributes
    ----------
    rename : Method
        Alias to rename_list[0] for backward compatibility.
    rename_list : list[Method], len(rename_list) == `superscalarity`
        List with the `superscalarity` rename methods. Each method can handle
        one renaime request. Each request consists of two
        source registers to be renamed and a pair of logical and
        physical destination registers ids. This pair represents a
        mapping to be added to RAT. There are no checks for conflicts
        between mappings inserted by different methods simultaneusly.
        Layout: RATLayouts.rat_rename_*
    """

    def __init__(self, *, gen_params: GenParams, superscalarity: int = 1, zero_init : bool = True):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        superscalarity : int
            Number of the rename methods to create.
        zero_init : int
            If True initialise content on reset with 0, else initialise with register
            logical id.
        """
        self.gen_params = gen_params
        self.superscalarity = superscalarity
        self.layouts = gen_params.get(RATLayouts)
        self.zero_init = zero_init

        self.entries = Array(Signal(self.gen_params.phys_regs_bits, reset = 0 if self.zero_init else i) for i in range(self.gen_params.isa.reg_cnt))

        if self.superscalarity < 1:
            raise ValueError(f"FRAT should have minimum one method, so superscalarity>=1, got: {self.superscalarity}")

        self.set_rename_list = [Method(i=self.layouts.set_rename_in) for _ in range(self.superscalarity)]
        self.get_rename_list = [
            Method(i=self.layouts.get_rename_in, o=self.layouts.get_rename_out) for _ in range(self.superscalarity)
        ]

    def elaborate(self, platform):
        m = TModule()

        @loop_def_method(m, self.get_rename_list)
        def _(_, rl_s1: Value, rl_s2: Value):
            return {"rp_s1": self.entries[rl_s1], "rp_s2": self.entries[rl_s2]}

        @loop_def_method(m, self.set_rename_list)
        def _(_, rp_dst: Value, rl_dst: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)

        return m


class RRAT(Elaboratable):
    """Retirement Register Alias Table

    Register alias table of committed instructions. It represents the state of
    the CPU as seen by the programmer. It can handle up to `superscalarity` commits
    recuests in a cycle as long as the logical registers ids passed to the methods
    are different. There are no checks to catch the situation, where two methods
    try to update the same register simultaneusly.

    Attributes
    ----------
    commit : Method
        Alias to commit_list[0] for backward compatibility.
    commit_list : list[Method]
        List with the `superscalarity` commit methods. Each of them takes
        `rp_dst` and `rl_dst` and update mapping hold in RAT returning
        `old_rp_dst` which was previously mapped to `rl_dst`.
        Layout: RATLayouts.rat_commit_*
    """

    def __init__(self, *, gen_params: GenParams, superscalarity: int = 1, zero_init : bool = True):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        superscalarity : int
            Number of `commit` methods to create.
        zero_init : int
            If True initialise content on reset with 0, else initialise with register
            logical id.
        """
        self.gen_params = gen_params
        self.superscalarity = superscalarity
        self.zero_init = zero_init

        layouts = gen_params.get(RATLayouts)
        self.commit_input_layout = layouts.rat_commit_in
        self.commit_output_layout = layouts.rat_commit_out

        self.entries = Array(Signal(self.gen_params.phys_regs_bits, reset = 0 if self.zero_init else i) for i in range(self.gen_params.isa.reg_cnt))

        if self.superscalarity < 1:
            raise ValueError(f"FRAT should have minimum one method, so superscalarity>=1, got: {self.superscalarity}")
        self.commit_list = [
            Method(i=self.commit_input_layout, o=self.commit_output_layout) for _ in range(self.superscalarity)
        ]
        # for backward compatibility
        self.commit = self.commit_list[0]

    def elaborate(self, platform):
        m = TModule()

        @loop_def_method(m, self.commit_list)
        def _(_, rp_dst: Value, rl_dst: Value):
            m.d.sync += self.entries[rl_dst].eq(rp_dst)
            return {"old_rp_dst": self.entries[rl_dst]}

        return m
