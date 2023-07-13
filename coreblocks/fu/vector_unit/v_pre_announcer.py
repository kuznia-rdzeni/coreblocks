from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.utils.fifo import BasicFifo

__all__ = ["VectorPreAnnouncer"]

class VectorPreAnnouncer(Elaboratable):
    def __init__(self, gen_params:GenParams, retire_method_count : int):
        self.gen_params = gen_params
        self.retire_method_count = retire_method_count

        self.layouts = self.gen_params.get(FuncUnitLayouts)

        self.retire_list = [Method(i = self.layouts.accept) for _ in range(self.retire_method_count)]

        self.accept = Method(o= self.layouts.accept)

    def elaborate(self, platform):
        m = TModule()

        fifos = [BasicFifo(self.layouts.accept, 2) for _ in range(self.retire_method_count)]
        m.submodules.fifos = ModuleConnector(*fifos)
            
        @loop_def_method(m, self.retire_list)
        def _(i, arg):
            fifos[i].write(m, arg)

        connect = Connect(self.layouts.accept)
        many_to_one_connect = ManyToOneConnectTrans(get_results = [fifo.read for fifo in fifos], put_result = connect.write)

        m.submodules.connect = connect
        m.submodules.many_to_one_connect = many_to_one_connect

        self.accept.proxy(m, connect.read)

        return m
