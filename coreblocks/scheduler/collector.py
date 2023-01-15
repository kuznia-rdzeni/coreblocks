from amaranth import *

from coreblocks.params import GenParams, FuncUnitLayouts
from coreblocks.transactions import Method, Transaction, def_method
from coreblocks.transactions.lib import FIFO


# primitive sink for multiple instructions
class Collector(Elaboratable):
    def __init__(self, gen_params: GenParams, gets: list[Method]):
        self.gen_params = gen_params
        self.layout = gen_params.get(FuncUnitLayouts).accept
        self.gets = gets
        self.get_single = Method(o=self.layout)

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo = fifo = FIFO(self.layout, 2)

        @def_method(m, self.get_single)
        def _(arg):
            return fifo.read(m)

        for get in self.gets:
            with Transaction().body(m):
                res = get(m)
                fifo.write(m, res)

        return m
