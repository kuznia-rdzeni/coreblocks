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
        self.alloc = alloc
        self.get_rename1 = get_rename1
        self.get_rename2 = get_rename2
        self.set_rename = set_rename

        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.issue = Method(i = self.layouts.translator_out)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        @def_method(m, self.issue)
        def _(arg):
            rec = Record(self.layouts.alloc_rename_in)
            m.d.av_comb += assign(rec, arg)
            with m.If(arg.rp_dst.type == RegisterType.V):
                realy_rp_dst = self.alloc(m, reg_count=1)
                self.set_rename(m, rl_dst = arg.rp_dst.id, rp_dst = realy_rp_dst)
                m.d.av_comb += rec.rp_dst.id.eq(realy_rp_dst)
            rename_out1 = self.get_rename1(m, rl_s1 = arg.rp_s1.id, rl_s2 = arg.rp_s2.id)
            rename_out2 = self.get_rename1(m, rl_s1 = arg.rp_s3.id, rl_s2 = arg.rp_v0.id)
            m.d.av_comb += rec.rp_s1.id.eq(rename_out1.rp_s1)
            m.d.av_comb += rec.rp_s2.id.eq(rename_out1.rp_s2)
            m.d.av_comb += rec.rp_s3.id.eq(rename_out2.rp_s1)
            m.d.av_comb += rec.rp_v0.id.eq(rename_out2.rp_s2)
            return rec


        return m
