from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorExecutionEnder"]

class VectorExecutionEnder(Elaboratable):
    def __init__(self, gen_params:GenParams, retire : Method):
        self.gen_params = gen_params
        self.retire = retire

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.init = Method(i = self.layouts.ender_init_in)
        self.end = Method()

    def elaborate(self, platform):
        m = TModule()

        rp_dst_saved = Record(self.gen_params.get(CommonLayouts).p_register_entry)
        rob_id_saved = Signal(self.gen_params.rob_entries_bits)
        valid = Signal()

        self.end.schedule_before(self.init)
        @def_method(m, self.end, ready=valid)
        def _():
            self.retire(m, exception = 0, result = 0, rob_id = rob_id_saved, rp_dst = rp_dst_saved)
            m.d.sync += valid.eq(0)

        @def_method(m, self.init, ready = ~valid | self.end.run)
        def _(rp_dst, rob_id):
            m.d.sync += rp_dst_saved.eq(rp_dst)
            m.d.sync += rob_id_saved.eq(rob_id)
            m.d.sync += valid.eq(1)

        return m
