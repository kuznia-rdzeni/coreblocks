from amaranth import *

from coreblocks.params import GenParams
from coreblocks.params.layouts import FuncUnitLayouts
from coreblocks.transactions import Method, TModule, def_method

__all__ = ["ResultAnnouncement"]


class ResultAnnouncement(Elaboratable):
    """
    Simple result announce unit. It takes an executed instruction and sends
    its results to ROB, RF and RS. ROB marks the instruction as completed.
    The RF stores the result value of the instruction. The value
    is also sent to RS in case if there is an instruction which waits for
    this value.
    """

    def __init__(self, *, gen_params: GenParams, rob_mark_done: Method, rs_write_val: Method, rf_write_val: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        rob_mark_done : Method
            Method which is invoked to mark that instruction ended without exception.
            It uses layout with one field `rob_id`,
        rs_write_val : Method
            Method which is invoked to pass value which is an output of finished instruction
            to RS, so that RS can save it if there are instructions which wait for it.
            It uses layout with two fields `tag` and `value`.
        rf_write_val : Method
            Method which is invoked to save value which is an output of finished instruction to RF.
            It uses layout with two fields `reg_id` and `reg_val`.
        """

        layouts = gen_params.get(FuncUnitLayouts)

        self.m_rob_mark_done = rob_mark_done
        self.m_rs_write_val = rs_write_val
        self.m_rf_write_val = rf_write_val
        self.send_result = Method(i=layouts.send_result)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.send_result)
        def _(result, rob_id, rp_dst):
            self.m_rob_mark_done(m, rob_id=rob_id)
            self.m_rf_write_val(m, reg_id=rp_dst, reg_val=result)
            with m.If(rp_dst != 0):
                self.m_rs_write_val(m, tag=rp_dst, value=result)

        return m
