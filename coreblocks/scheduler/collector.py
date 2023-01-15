from amaranth import *

from coreblocks.params import GenParams, FuncUnitLayouts
from coreblocks.transactions import Method
from coreblocks.transactions.lib import FIFO, ManyToOneConnectTrans


# primitive sink for multiple instructions
class Collector(Elaboratable):
    def __init__(self, gen_params: GenParams, gets: list[Method]):
        self.gen_params = gen_params
        self.layout = gen_params.get(FuncUnitLayouts).accept
        self.gets = gets
        self.get_single = Method(o=self.layout)

    def elaborate(self, platform):
        m = Module()

        # TODO: find a way to remove this FIFO. It increases FU latency without need.
        m.submodules.fifo = fifo = FIFO(self.layout, 2)

        m.submodules.connect = ManyToOneConnectTrans(get_results=[get for get in self.gets], put_result=fifo.write)

        self.get_single.proxy(m, fifo.read)

        return m
