from amaranth import *
from ..transactions import Method
from ..params import GenParams, FetchLayouts
from ..layout import FetchLayouts

class BranchDetector(Elaboratable):
    def __init__(self, gen_params: GenParams, push_instr: Method):
        self.gen_params = gen_params
        self.pc = Signal(gen_params.isa.xlen, reset=gen_params.start_pc)
        self.push_instr = push_instr

        raw_instr_layout = gen_params.get(FetchLayouts).raw_instr
        self.detect = Method(i=raw_instr_layout, o=raw_instr_layout)
        self.branch_verify = Method(i=32) # TODO: custom layout

    def elaborate(self, platform):
        m = Module()

        stalled = Signal()
        drop_next_instr = Signal()

        @def_method(m, self.detect, ready=(~stalled))
        def _(arg):
            # 3 MSBs of opcode are enough to determine if instruction is a jump/branch
            is_branch = arg.data[4:7] == 0b110
            m.d.sync += stalled.eq(is_branch)

            # this is a bit awkward - since we don't have state recovery we potentially
            # need to drop instruction that lies directly after the branch and was
            # already fetched but is from the wrong path
            with m.If(drop_next_instr):
                m.d.sync += drop_next_instr.eq(0)
                next_pc = self.pc  # self.pc is from the resolved branch
            with m.Else():
                next_pc = self.pc + self.gp.isa.ilen_bytes
                self.push_instr(m, {
                    "data": arg.data,
                    "pc": self.pc
                })

            return {"next_pc": next_pc}

        @def_method (m, self.branch_verify, ready=stalled)
        def _(arg):
            m.d.sync += self.pc.eq(arg.pc)
            m.d.sync += stalled.eq(0)
            m.d.sync += drop_next_instr.eq(arg.taken)

        return m