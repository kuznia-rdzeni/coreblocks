from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import BasicFifo

__all__ = ["VectorAnnouncer"]


class VectorAnnouncer(Elaboratable):
    """ Collects announces about end of instruction processing and sends them to the scalar core

    Attributes
    ----------
    announce_list : list[Method]
        Methods to be called when the vector unit has finished processing of an instruction.
        Layout: FuncUnitLayouts.accept
    accept : Method
        Method to be called by the scalar core to get information about completed instructions.
    """
    def __init__(self, gen_params: GenParams, announce_method_count: int):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        announce_method_count : int
            The number of methods to created in the `announce_list`.
        """
        self.gen_params = gen_params
        self.announce_method_count = announce_method_count

        self.layouts = self.gen_params.get(FuncUnitLayouts)

        self.announce_list = [Method(i=self.layouts.accept) for _ in range(self.announce_method_count)]

        self.accept = Method(o=self.layouts.accept)

    def elaborate(self, platform):
        m = TModule()

        fifos = [BasicFifo(self.layouts.accept, 2) for _ in range(self.announce_method_count)]
        m.submodules.fifos = ModuleConnector(*fifos)

        @loop_def_method(m, self.announce_list)
        def _(i, arg):
            fifos[i].write(m, arg)

        connect = Connect(self.layouts.accept)
        many_to_one_connect = ManyToOneConnectTrans(get_results=[fifo.read for fifo in fifos], put_result=connect.write)

        m.submodules.connect = connect
        m.submodules.many_to_one_connect = many_to_one_connect

        self.accept.proxy(m, connect.read)

        return m
