from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorRetirement"]


class VectorRetirement(Elaboratable):
    """ Retirement of the vector instructions

    The module stores completed vector instructions in the
    content adressable memory and checks on each precommit call
    whether the currently retired instruction is in the memory.
    If is is, then it is removed from it, VRRAT is updated,
    and the old VRRAT entr is dealocated.

    Attributes
    ----------
    precommit : Method
        Method called by the scalar retirement to notify that a
        instruction is being to be committed.
    report_end : Method
        Called by the `VectorExecutionEnder` to mark that the
        instruction finished execution.
    """
    def __init__(self, gen_params: GenParams, instr_to_retire_count: int, v_rrat_commit: Method, deallocate: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration
        instr_to_retire_count : int
            Number of slots to prepare in content addressable
            memory to store instructions that waiting to be retired.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.instr_to_retire_count = instr_to_retire_count
        self.v_rrat_commit = v_rrat_commit
        self.deallocate = deallocate

        self.x_retirement_layouts = self.gen_params.get(RetirementLayouts)
        self.v_retirement_layouts = self.gen_params.get(VectorRetirementLayouts)

        self.precommit = Method(i=self.x_retirement_layouts.precommit)
        self.report_end = Method(i=self.v_retirement_layouts.report_end)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        camemory = ContentAddressableMemory(
            [("rob_id", self.gen_params.rob_entries_bits)],
            [("rp_dst", self.gen_params.get(CommonLayouts).p_register_entry)],
            self.instr_to_retire_count,
        )
        m.submodules.camemory = camemory

        rob_peek = self.gen_params.get(DependencyManager).get_dependency(ROBPeekKey())

        @def_method(m, self.report_end)
        def _(rob_id, rp_dst):
            camemory.push(m, addr=rob_id, data={"rp_dst": rp_dst})

        @def_method(m, self.precommit)
        def _(rob_id):
            response = camemory.pop(m, addr=rob_id)
            rob_response = rob_peek(m)
            with m.If(~response.not_found & (response.data.rp_dst.type == RegisterType.V)):
                resp = self.v_rrat_commit(m, rp_dst=response.data.rp_dst.id, rl_dst=rob_response.rob_data.rl_dst.id)
                cast_old_rp_dst = Signal(self.v_params.vrp_count_bits)
                m.d.top_comb += cast_old_rp_dst.eq(resp.old_rp_dst)
                self.deallocate(m, reg=cast_old_rp_dst)

        return m
