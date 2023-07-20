from amaranth import *
from coreblocks.transactions import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorNeededRegs"]


class VectorNeededRegs(Elaboratable):
    """ Module to check which registers are needed to execute the instruction.

    Actually only arithmetic two source instructions are supported.

    Attributes
    ----------
    issue : Method
        Get the required registers for a new instruction.
    """
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.executor_in, o=self.layouts.needed_regs_out)

    def elaborate(self, platform):
        m = TModule()

        rec_out = Record(self.layouts.needed_regs_out)

        @def_method(m, self.issue)
        def _(arg):
            m.d.top_comb += [
                rec_out.v0_needed.eq(arg.vtype.ma == 0),
                rec_out.s1_needed.eq(arg.rp_s1.type == RegisterType.V),
                rec_out.s2_needed.eq(1),
                # There is no support for three source instructions yet (interger multiply-add)
                rec_out.s3_needed.eq(0),
            ]
            return rec_out

        return m
