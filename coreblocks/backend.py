from amaranth import *
from coreblocks.transactions import Method, Transaction
from coreblocks.transactions._utils import Scheduler as RoundRobinOneHot
from coreblocks.transactions._utils import OneHotSwitch
from coreblocks.transactions.lib import ConnectTrans
from coreblocks.layouts import *
from coreblocks.genparams import GenParams

__all__ = ["ResultAnnouncement"]


class ResultAnnouncement(Elaboratable):
    def __init__(
        self, *, gen: GenParams, get_result: Method, rob_mark_done: Method, rs_write_val: Method, rf_write_val: Method
    ):
        """
        Simple result announce unit. It take an executed instruction and send
        its results to ROB, RF and RS. In ROB there is written, that instruction
        ended its execution, in RF there is saved value of instruction. Value
        is also send to RS in case if there is an instruction which wait for
        this value.

        Method `get_result` get already serialized instruction results, so in
        case in which we have more than one FU, then they outputs should be connected by
        `ManyToOneConnectTrans` to FIFO.

        Parameters
        ----------
        gen : GenParams
            Instance of GenParams with parameters which should be used to generate
            fetch unit.
        get_result : Method
            Method which is invoked to get results of next ready instruction,
            which should be announced in core. This method assume, that results
            from different FUs are already serialized.
        rob_mark_done : Method
            Method which is invoked to mark that instruction ended without exception.
            It use layout with one field "rob_id",
        rs_write_val : Method
            Method which is invoked to pass  value which is an output of ended instruction
            to RS, so that RS can save it if there are instructions which wait for it.
            It use layout with two fields "tag" and "value".
        rf_write_val : Method
            Method which is invoked to save value which is an output of ended instruction to RF.
            It use layout with two fields "reg_id" and "reg_val".
        """
        self.m_get_result = get_result
        self.m_rob_mark_done = rob_mark_done
        self.m_rs_write_val = rs_write_val
        self.m_rf_write_val = rf_write_val

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            result = self.m_get_result(m)
            self.m_rob_mark_done(m, {"rob_id": result.rob_id})
            with m.If(result.rp_dst != 0):
                self.m_rf_write_val(m, {"reg_id": result.rp_dst, "reg_val": result.result})
                self.m_rs_write_val(m, {"tag": result.rp_dst, "value": result.result})

        return m
