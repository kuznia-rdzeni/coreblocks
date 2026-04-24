from amaranth import *

from coreblocks.params import GenParams
from coreblocks.interface.layouts import FuncUnitLayouts, RFLayouts, ROBLayouts, RSLayouts
from transactron import Method, Provided, Required, TModule, def_method

__all__ = ["ResultAnnouncement"]


class ResultAnnouncement(Elaboratable):
    """
    Simple result announce unit. It takes an executed instruction and sends
    its results to ROB, RF and RS. ROB marks the instruction as completed.
    The RF stores the result value of the instruction. The value
    is also sent to RS in case if there is an instruction which waits for
    this value.

    Attributes
    ----------
    push_result : Method, provided
        Should be called to perform result announcement.
    rob_mark_done : Method, required
        Method which is invoked to mark that instruction ended.
    rs_update : Method, required
        Method which is invoked to pass value which is an output of finished instruction
        to RS, so that RS can save it if there are instructions which wait for it.
    rf_write : Method, required
        Method which is invoked to save value which is an output of finished instruction to RF.
    """

    push_result: Provided[Method]
    rob_mark_done: Required[Method]
    rs_update: Required[Method]
    rf_write_val: Required[Method]

    def __init__(self, *, gen_params: GenParams):
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        """

        self.push_result = Method(i=gen_params.get(FuncUnitLayouts).push_result)
        self.rob_mark_done = Method(i=gen_params.get(ROBLayouts).mark_done_layout)
        self.rs_update = Method(i=gen_params.get(RSLayouts, rs_entries=gen_params.max_rs_entries).rs.update_in)
        self.rf_write_val = Method(i=gen_params.get(RFLayouts).rf_write)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.push_result)
        def _(result, rob_id, rp_dst, exception):
            self.rob_mark_done(m, rob_id=rob_id, exception=exception)

            self.rf_write_val(m, reg_id=rp_dst, reg_val=result)
            with m.If(rp_dst != 0):
                self.rs_update(m, reg_id=rp_dst, reg_val=result)

        return m
