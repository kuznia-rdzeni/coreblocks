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
        self.m_get_result = get_result
        self.m_rob_mark_done = rob_mark_done
        self.m_rs_write_val = rs_write_val
        self.m_rf_write_val = rf_write_val

        self.lay_result = gen.get(FuncUnitLayouts).accept
        self.lay_rob_mark_done = gen.get(ROBLayouts).id_layout
        self.lay_rs_write = gen.get(RSLayouts).insert_in
        self.lay_rf_write = gen.get(RFLayouts).rf_write

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            result = self.m_get_result(m)
            self.m_rob_mark_done(m, {"rob_id": result.rob_id})
            self.m_rf_write_val(m, {"reg_id": result.rp_dst, "reg_val": result.result})
            self.m_rs_write_val(m, {"tag": result.rp_dst, "value": result.result})

        return m
