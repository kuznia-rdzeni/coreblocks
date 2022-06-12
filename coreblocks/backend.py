from amaranth import *
from coreblocks.transactions import Method, Transaction
from coreblocks.transactions._utils import Scheduler as RoundRobinOneHot
from coreblocks.transactions._utils import OneHotSwitch
from coreblocks.layouts import FuncUnitLayouts
from coreblocks.genparams import GenParams


def FUArbitration(Elaboratable):
    def __init__(self, *, gen: GenParams, get_results: list[Method], put_result: Method):
        self.lay_result = gen.get(FuncUnitLayouts).accept

        self.get_results = get_results
        self.m_put_result = put_result

        self.count = len(self.get_results)

    def elaborate(self, platfrom):
        m = Module()

        m.submodules.rr = rr = RoundRobinOneHot(self.count)

        for i in range(self.count):
            m.comb += rr.requests[i].eq(self.get_results[i].ready)

        data = Record(self.lay_result)

        with Transaction().body(m, request=rr.valid):
            with OneHotSwitch(m, rr.grant) as i:
                m.comb += data.eq(self.get_results[i](m))
            m.comb += self.m_put_result(m,data)

        return m


def ResultAnnouncemet(Elaboratable):
    def __init__(self, *, gen:GenParams, get_result: Method, rob_mark_done: Method,
            rs_write_val : Method, rf_write_val : Method):
        self.m_get_result = get_result
        self.m_rob_mark_done = mark_done
        self.m_rs_write_val = rs_write_val
        self.m_rf_write_val = rf_write_val

        self.lay_result = gen.get(FuncUnitLayouts).accept
        self.lay_rob_mark_done = gen.get(ROBLayouts).id_layout
        self.lay_rs_write = gen.get(RSLayouts).rs_announce_val
        self.lay_rf_write = gen.get(RFLayouts).rf_write

    def elaborate(self, platform):
        m = Module()

        result = Record(self.lay_result)
        rob_data = Record(self.lay_rob_mark_done)
        m.comb += rob_data.rob_id.eq(result.instr_tag)

        rf_data = Record(self.lay_rf_write)
        m.comb += [ 
            rf_data.reg_id.eq(result.rp_dst),
            rf_data.reg_val.eq(result.result)
            ]

        rs_data = Record(self.lay_rs_write)
        m.comb += [
            rs_data.reg_id.eq(result.rp_dst),
            rs_data.value.eq(result.result)
            ]

        with Transaction().body(m):
            m.comb += result.eq(self.m_get_result(m))
            self.m_rob_mark_done(m, rob_data)
            self.m_rf_write_val(m, rf_data)
            self.m_rs_write_val(m, rs_data)

        return m
