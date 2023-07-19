from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorAllocRename"]


class VectorAllocRename(Elaboratable):
    """Allocate and rename vector registers

    Module for allocating and renaming vector registers using the vector
    register alias table and vector FreeRF file.

    Attributes
    ----------
    issue : Method(i=VectorFrontendLayouts.alloc_rename_in, o= VectorFrontendLayouts.alloc_rename_out)
        Method to send the instruction to be renamed. If `rp_dst` has `RegisterType.V` then a
        new physical vector register is allocated and VFRAT will be updated.
    """

    def __init__(
        self,
        gen_params: GenParams,
        alloc: Method,
        get_rename1: Method,
        get_rename2: Method,
        set_rename: Method,
        initialise_regs: list[Method],
    ):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        alloc : Method(i=SuperscalarFreeRFLayouts.allocate_in)
            Method to allocate a register.
        get_rename1 : Method(i=RATLayouts.get_rename_in, o=RATLayouts.get_rename_out)
            Method to get the renaming of registers.
        get_rename2 : Method
            The same as `get_rename1` but an another instance, to allow for renaming of 4
            registers at a time.
        set_rename : Method
            Method used to update the VFRAT.
        initialise_regs : list[Method]
            Methods called to initialise newly allocated register.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.alloc = NotMethod(alloc)
        self.get_rename1 = get_rename1
        self.get_rename2 = get_rename2
        self.set_rename = set_rename
        self.initialise_regs = initialise_regs

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.issue = Method(i=self.layouts.alloc_rename_in, o=self.layouts.alloc_rename_out)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        @def_method(m, self.issue)
        def _(arg):
            rec = Record(self.layouts.alloc_rename_in)
            m.d.av_comb += assign(rec, arg)
            with m.If(arg.rp_dst.type == RegisterType.V):
                # "real" rp_dst, because till now in "rp_dst" there is
                # logical vector rp_dst copied here by scalar RS
                real_rp_dst = self.alloc.method(m, reg_count=1)
                # we are downcasting back to reg_cnt_log, because it conatins
                # real logical id, but was increased in size due to renaiming in X scheduler
                rec_rename = Record(self.set_rename.data_in.layout)
                m.d.top_comb += rec_rename.rl_dst.eq(arg.rp_dst.id)
                m.d.top_comb += rec_rename.rp_dst.eq(real_rp_dst)
                self.set_rename(m, rec_rename)
                m.d.av_comb += rec.rp_dst.id.eq(real_rp_dst)
                with m.Switch(real_rp_dst):
                    for i in range(self.v_params.vrp_count):
                        with m.Case(i):
                            self.initialise_regs[i](m)
            rec_get_1 = Record(self.get_rename1.data_in.layout)
            rec_get_2 = Record(self.get_rename2.data_in.layout)
            m.d.top_comb += rec_get_1.rl_s1.eq(arg.rp_s1.id)
            m.d.top_comb += rec_get_1.rl_s2.eq(arg.rp_s2.id)
            m.d.top_comb += rec_get_2.rl_s1.eq(arg.rp_s3.id)
            m.d.top_comb += rec_get_2.rl_s2.eq(arg.rp_v0.id)
            rename_out1 = self.get_rename1(m, rec_get_1)
            rename_out2 = self.get_rename2(m, rec_get_2)
            m.d.av_comb += rec.rp_s1.id.eq(rename_out1.rp_s1)
            m.d.av_comb += rec.rp_s2.id.eq(rename_out1.rp_s2)
            m.d.av_comb += rec.rp_s3.id.eq(rename_out2.rp_s1)
            m.d.av_comb += rec.rp_v0.id.eq(rename_out2.rp_s2)
            return rec

        return m
