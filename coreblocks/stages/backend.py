from amaranth import *

from coreblocks.params import GenParams
from transactron import Method, Transaction, TModule

__all__ = ["ResultAnnouncement"]


class ResultAnnouncement(Elaboratable):
    """
    Simple result announce unit. It takes an executed instruction and sends
    its results to ROB, RF and RS. ROB marks the instruction as completed.
    The RF stores the result value of the instruction. The value
    is also sent to RS in case if there is an instruction which waits for
    this value.

    Method `get_result` gets already serialized instruction results, so in
    case in which we have more than one FU, then their outputs should be connected by
    `ManyToOneConnectTrans` to a FIFO.
    """

    def __init__(
        self, *, gen: GenParams, get_result: Method, rob_mark_done: Method, rs_update: Method, rf_write: Method
    ):
        """
        Parameters
        ----------
        gen : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        get_result : Method
            Method which is invoked to get results of next ready instruction,
            which should be announced in core. This method assumes that results
            from different FUs are already serialized.
        rob_mark_done : Method
            Method which is invoked to mark that instruction ended without exception.
        rs_update : Method
            Method which is invoked to pass value which is an output of finished instruction
            to RS, so that RS can save it if there are instructions which wait for it.
        rf_write : Method
            Method which is invoked to save value which is an output of finished instruction to RF.
        """

        self.m_get_result = get_result
        self.m_rob_mark_done = rob_mark_done
        self.m_rs_update = rs_update
        self.m_rf_write_val = rf_write

    def debug_signals(self):
        return [self.m_get_result.debug_signals()]

    def elaborate(self, platform):
        m = TModule()

        with Transaction().body(m):
            result = self.m_get_result(m)
            self.m_rob_mark_done(m, rob_id=result.rob_id, exception=result.exception)

            with m.If(result.exception == 0):
                self.m_rf_write_val(m, reg_id=result.rp_dst, reg_val=result.result)
                with m.If(result.rp_dst != 0):
                    self.m_rs_update(m, reg_id=result.rp_dst, reg_val=result.result)

        return m
