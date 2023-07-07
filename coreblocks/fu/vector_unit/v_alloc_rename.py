from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.utils._typing import ValueLike

__all__ = ["VectorAllocRename"]

class VectorAllocRename(Elaboratable):
    def __init__(self, gen_params : GenParams, v_params : VectorParameters, alloc : Method, get_rename1 : Method, get_rename2 : Method, set_rename : Method):
        self.gen_params = gen_params
        self.v_params = v_params
        self.alloc = NotMethod(alloc)
        self.get_rename1 = get_rename1
        self.get_rename2 = get_rename2
        self.set_rename = set_rename

        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.issue = Method(i = self.layouts.alloc_rename_in, o = self.layouts.alloc_rename_out)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        @def_method(m, self.issue)
        def _(arg):
            rec = Record(self.layouts.alloc_rename_in)
            m.d.av_comb += assign(rec, arg)
            with m.If(arg.rp_dst.type == RegisterType.V):
                realy_rp_dst = self.alloc.method(m, reg_count=1)
                # we are downcasting back to reg_cnt_log, because it conatins
                # real logical id, but was increased in size due to renaiming in X scheduler
                rec_rename = Record(self.set_rename.data_in.layout)
                m.d.top_comb += rec_rename.rl_dst.eq(arg.rp_dst.id)
                m.d.top_comb += rec_rename.rp_dst.eq(realy_rp_dst)
                self.set_rename(m, rec_rename)
                m.d.av_comb += rec.rp_dst.id.eq(realy_rp_dst)
            rec_get_1 = Record(self.get_rename1.data_in.layout)
            rec_get_2 = Record(self.get_rename2.data_in.layout)
            m.d.top_comb += rec_get_1.rl_s1.eq(arg.rp_s1.id)
            m.d.top_comb += rec_get_1.rl_s1.eq(arg.rp_s2.id)
            m.d.top_comb += rec_get_2.rl_s1.eq(arg.rp_s3.id)
            m.d.top_comb += rec_get_2.rl_s1.eq(arg.rp_v0.id)
            rename_out1 = self.get_rename1(m, rec_get_1)
            rename_out2 = self.get_rename2(m, rec_get_2)
            m.d.av_comb += rec.rp_s1.id.eq(rename_out1.rp_s1)
            m.d.av_comb += rec.rp_s2.id.eq(rename_out1.rp_s2)
            m.d.av_comb += rec.rp_s3.id.eq(rename_out2.rp_s1)
            m.d.av_comb += rec.rp_v0.id.eq(rename_out2.rp_s2)
            return rec


        return m
